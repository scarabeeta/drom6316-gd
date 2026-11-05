#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# drom6316flash - firmware flasher for the PHILIPS DVD-ROM DROM6316 (MediaTek MT1359SE, Winbond
# W25B20A 256 KiB SPI flash) on Linux, using the drive's own WRITE BUFFER path.
USAGE = '''usage: drom6316flash.py read <out.bin>          read the whole flash (256 KiB)
       drom6316flash.py <image.bin>               dry run: compare, send nothing but reads
       drom6316flash.py <image.bin> stage         upload to drive DRAM and read it back; no flash write
       drom6316flash.py <image.bin> go [rewrite] [force]
                                                  write; 'rewrite' also writes an identical image
                                                  (A->A test of the write path)
The drive is found by its INQUIRY model; set SGDEV=/dev/sgN to pick it explicitly.'''
#
# Protocol (static analysis of the Dell XFLASH tool ODNKDOS.EXE and of ODNK firmware):
#   read    3C 04 00 A2 A1 A0 00 PP 00 ..   READ BUFFER mode 4: firmware SPI read (03), PP pages of 256 B
#   upload  3B 06 00 A2 A1 A0 00 40 00 00   WRITE BUFFER mode 6: 16 KiB into drive DRAM, no flash access
#   check   3C 02 00 A2 A1 A0 00 40 00 00   READ BUFFER mode 2: read the same DRAM back
#   commit  3B 07 00 00 ..                  WRITE BUFFER mode 7: the drive erases and programs
#                                           0x8000-0x3FFFF from DRAM, verifying every page
# The drive never writes 0x0000-0x7FFF (boot loader, and the NV sector with this unit's data), so
# those bytes of the image do not matter. It programs the main entry bytes at 0x8000/0x8003 last.
# After the commit the drive is expected to sit in its boot loader until it is power-cycled;
# power-cycle it, then run the dry run again: it must report 0 bytes differ.
#
# Safety:
# - Every flash read is done twice and must agree.
# - The image must be for this drive: the INQUIRY model string must sit at the same offsets in
#   the image and in the current flash, and the main entry must be the same LJMP opcode.
# - The image must carry a correct firmware checksum (16-bit sum of 0x8000-0x3FFFB at 0x3FFFE),
#   so a damaged or hand-edited image is refused. Dell's ODFN.BIN ships with a wrong one.
# - Before writing, the current flash is saved to drom6316flash-backup-<time>.bin.
# - Each 16 KiB upload is read back; before the commit the whole 256 KiB in DRAM is read back
#   once more and must equal the image. Nothing reaches the flash before that.
# - Do not power-cycle the drive while the commit command is running.
import ctypes, errno, fcntl, glob, os, struct, sys, time

MODEL = b'DVD-ROM DROM6316'
FLASH = 0x40000
MAIN = 0x8000                 # first byte the drive programs
CHUNK = 0x4000                # upload size used by the official tool
READ_PAGES = 16               # pages of 256 B per READ BUFFER mode 4 command
FLASH_READ_TRIES = 3          # total attempts for transient mode-4 read failures
FLASH_READ_RETRY_DELAY = 1    # seconds between attempts at the same offset
SUM = 0x3FFFE                 # image checksum word
SG_IO = 0x2285
_fd = -1


def cam(cdb, din=0, dout=None, timeout=60):
    """Returns (ok, data, description, (sense key, asc, ascq))."""
    if dout is not None:
        n, direction = len(dout), -2
        buf = ctypes.create_string_buffer(bytes(dout), max(n, 1))
    else:
        n, direction = din, (-3 if din else -1)
        buf = ctypes.create_string_buffer(max(n, 1))
    sense = ctypes.create_string_buffer(32)
    c = ctypes.create_string_buffer(bytes(cdb))
    hdr = bytearray(struct.pack('iiBBHIPPPIIiPBBBBHHiII', ord('S'), direction, len(cdb), 32, 0, n,
                    ctypes.addressof(buf), ctypes.addressof(c), ctypes.addressof(sense),
                    timeout * 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    fcntl.ioctl(_fd, SG_IO, hdr)
    f = struct.unpack('iiBBHIPPPIIiPBBBBHHiII', bytes(hdr))
    status, host, drv, resid = f[13], f[17], f[18], f[19]
    # drv & 0xF includes DRIVER_SENSE: sense data with GOOD status still counts as a failure
    ok = status == 0 and host == 0 and (drv & 0xF) == 0 and resid == 0
    sb = sense.raw
    key = (sb[2] & 15, sb[12], sb[13])
    return ok, buf.raw[:din] if din else b'', 'sense %X/%02X/%02X st%d h%d d%d resid%d' % (key + (status, host, drv, resid)), key


def must(res, what):
    if not res[0]:
        raise SystemExit('%s FAILED: %s' % (what, res[2]))
    print('  ok:', what, flush=True)


def C(*b):
    return list(b) + [0] * (12 - len(b))


def a24(a):
    return (a >> 16) & 255, (a >> 8) & 255, a & 255


def find_drive():
    """The sg node of the one attached DROM6316, by sysfs model (node numbers change)."""
    hits = []
    for g in glob.glob('/sys/class/scsi_generic/sg*'):
        try:
            model = open(g + '/device/model', 'rb').read().strip()
        except OSError:
            continue
        if model == MODEL:
            hits.append('/dev/' + os.path.basename(g))
    if len(hits) != 1:
        sys.exit('expected exactly one %s, found %d; set SGDEV to choose' % (MODEL.decode(), len(hits)))
    return hits[0]


def wait_ready(limit=60):
    """Wait until the drive has finished starting up. 'No medium' counts as ready."""
    end = time.time() + limit
    while True:
        ok, _, err, key = cam([0, 0, 0, 0, 0, 0])
        if ok or (key[0] == 2 and key[1] == 0x3A):
            return
        if time.time() > end:
            raise SystemExit('drive not ready after %d s: %s' % (limit, err))
        time.sleep(1)


def inquiry():
    ok, d, err, _ = cam([0x12, 0, 0, 0, 0x24, 0], din=0x24)
    if not ok or len(d) < 0x24:
        raise SystemExit('INQUIRY failed: ' + err)
    return d[8:16], d[16:32], d[32:36]


def read_pass():
    out = bytearray()
    step = READ_PAGES * 0x100
    for a in range(0, FLASH, step):
        cdb = C(0x3C, 0x04, 0, *a24(a), 0, READ_PAGES)
        for attempt in range(1, FLASH_READ_TRIES + 1):
            ok, d, err, key = cam(cdb, din=step)
            if ok:
                break
            transient = key is not None and (
                (key[0] == 2 and key[1] in (0x3A, 0x04)) or
                (key[0] == 6 and key[1] in (0x28, 0x29)))
            if not transient or attempt == FLASH_READ_TRIES:
                raise SystemExit('flash read @%#x failed (attempt %d/%d): %s'
                                 % (a, attempt, FLASH_READ_TRIES, err))
            print('  flash read @%#x failed (attempt %d/%d): %s; retrying the same read...'
                  % (a, attempt, FLASH_READ_TRIES, err), flush=True)
            time.sleep(FLASH_READ_RETRY_DELAY)
        out += d
    return bytes(out)


def read_flash():
    """Read the flash until two consecutive passes agree."""
    wait_ready()
    prev = read_pass()
    for _ in range(4):
        cur = read_pass()
        if cur == prev:
            return cur
        n = sum(1 for i in range(FLASH) if cur[i] != prev[i])
        print('  two reads differ in %d bytes (drive still starting up?), reading again...' % n, flush=True)
        prev = cur
        time.sleep(2)
    raise SystemExit('flash reads keep changing; not trusting them')


def find_all(data, pat, start=0):
    out, i = [], data.find(pat, start)
    while i >= 0:
        out.append(i)
        i = data.find(pat, i + 1)
    return out


def image_sum(d):
    """The firmware's own checksum (bank0 CCEE, E6 02 self test): 16-bit sum of 0x8000-0x3FFFB,
    stored big endian at 0x3FFFE."""
    return sum(d[MAIN:SUM - 2]) & 0xFFFF


def check_image(before, img):
    """Reasons why img does not look like firmware for the drive whose flash is before."""
    cur = find_all(before, MODEL, MAIN)
    if not cur:
        return ['the current flash does not contain %r (unsupported drive?)' % MODEL.decode()]
    why = []
    new = find_all(img, MODEL, MAIN)
    if not new:
        why.append('the image does not contain %r: it is for another model' % MODEL.decode())
    elif new != cur:
        why.append('the image has the model string at %s, the drive at %s: different firmware layout'
                   % ([hex(o) for o in new], [hex(o) for o in cur]))
    stored, computed = int.from_bytes(img[SUM:SUM + 2], 'big'), image_sum(img)
    if stored != computed:
        why.append('image checksum at %#x is %04X, the image sums to %04X: corrupt or hand-edited image'
                   % (SUM, stored, computed))
    for o in (MAIN, MAIN + 3):
        # the drive programs 02 here itself, last; anything else means a different layout
        if img[o] != 0x02 or before[o] != 0x02:
            why.append('main entry byte %#x is %02X in the image and %02X in the drive (expected 02)'
                       % (o, img[o], before[o]))
    return why


def upload(img, tries=3):
    """Send the image into drive DRAM in the official 16 KiB steps, checking each step."""
    for a in range(0, FLASH, CHUNK):
        part = img[a:a + CHUNK]
        for attempt in range(1, tries + 1):
            res = cam(C(0x3B, 0x06, 0, *a24(a), *a24(CHUNK)), dout=part)
            if res[0]:
                res = cam(C(0x3C, 0x02, 0, *a24(a), *a24(CHUNK)), din=CHUNK)
                if res[0] and res[1] != part:
                    res = (False, b'', 'read-back differs', None)
            if res[0]:
                break
            print('  upload %#07x failed (attempt %d/%d): %s' % (a, attempt, tries, res[2]), flush=True)
        else:
            raise SystemExit('upload @%#x failed; nothing was written to flash' % a)
    print('  ok: uploaded 256 KiB to drive DRAM', flush=True)


def dram_matches(img):
    """Read the whole DRAM copy back once more; the commit is only sent when it equals the image."""
    out = bytearray()
    for a in range(0, FLASH, CHUNK):
        ok, d, err, _ = cam(C(0x3C, 0x02, 0, *a24(a), *a24(CHUNK)), din=CHUNK)
        if not ok:
            print('  DRAM read-back @%#x failed: %s' % (a, err))
            return False
        out += d
    bad = [i for i in range(MAIN, FLASH) if out[i] != img[i]]
    if bad:
        print('  DRAM copy differs from the image in %d bytes from %#x on' % (len(bad), bad[0]))
        return False
    print('  ok: DRAM copy of 0x8000-0x3FFFF equals the image', flush=True)
    return True


def main():
    global _fd
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help') or (args[0] == 'read' and len(args) != 2):
        sys.exit(USAGE)
    reading = args[0] == 'read'
    words = args[1:] if not reading else []
    if words and (words[0] not in ('stage', 'go') or (words[0] == 'stage' and len(words) > 1)
                  or any(w not in ('rewrite', 'force') for w in words[1:]) or len(set(words)) != len(words)):
        sys.exit(USAGE)
    stage, go = words[:1] == ['stage'], words[:1] == ['go']
    rewrite, force = 'rewrite' in words, 'force' in words
    if not reading:
        img = open(args[0], 'rb').read()
        if len(img) != FLASH:
            sys.exit('%s is %d bytes; a flash image is %d bytes' % (args[0], len(img), FLASH))

    dev = os.environ.get('SGDEV') or find_drive()
    flags = os.O_RDWR | os.O_NONBLOCK
    try:
        # exclusive when sending writes: refuse a drive some other program has open
        _fd = os.open(dev, flags | (os.O_EXCL if (go or stage) else 0))
    except OSError as e:
        if e.errno == errno.EBUSY:
            sys.exit('%s is in use by another program; not writing to a drive that is being used' % dev)
        sys.exit('cannot open %s: %s' % (dev, e.strerror))

    vendor, product, rev = inquiry()
    print('drive: %r %r rev %r' % (vendor.decode('latin1'), product.decode('latin1'), rev.decode('latin1')), flush=True)
    if product != MODEL:
        sys.exit('this is not a %s' % MODEL.decode())
    if rev == b'ODBO':
        sys.exit('the drive is in its boot loader (rev ODBO); power-cycle it first. Boot-loader '
                 'flashing is not implemented.')
    print('reading current flash (twice)...', flush=True)
    before = read_flash()

    if reading:
        if not find_all(before, MODEL, MAIN):
            sys.exit('the data read does not contain %r; not saving it' % MODEL.decode())
        open(args[1], 'wb').write(before)
        print('dumped to', args[1])
        return

    why = check_image(before, img)
    for w in why:
        print('  image check:', w)
    diffs = [i for i in range(MAIN, FLASH) if before[i] != img[i]]
    low = sum(1 for i in range(MAIN) if before[i] != img[i])
    print('main 0x8000-0x3FFFF: %d bytes differ' % len(diffs), flush=True)
    print('boot/NV 0x0000-0x7FFF: %d bytes differ (never written by the drive; informational)' % low, flush=True)
    if not (go or stage):
        print('DRY-RUN: nothing sent but reads' + ('; this image would be REFUSED' if why else ''))
        return
    if why and not force:
        sys.exit("REFUSING: the image does not match this drive (see 'image check' above). 'force' overrides.")

    # spin down first, as the official tool does; no medium is fine
    cam(C(0x1B, 0x01, 0, 0, 0x00))
    if stage:
        print('== STAGING', args[0], '(DRAM only, no flash write) ==', flush=True)
        upload(img)
        dram_matches(img)
        print('staged only. The flash is unchanged; power-cycle the drive to clear its DRAM state.')
        return
    if not diffs and not rewrite:
        print("main area identical; nothing to do ('rewrite' writes it anyway)")
        return

    backup = 'drom6316flash-backup-%s.bin' % time.strftime('%Y%m%d-%H%M%S')
    open(backup, 'wb').write(before)
    print('current flash saved to', backup, flush=True)
    print('== FLASHING', args[0], '==', flush=True)
    upload(img)
    if not dram_matches(img):
        sys.exit('DRAM copy is wrong; NOT committing. The flash is unchanged; power-cycle the drive.')
    print('  committing (WRITE BUFFER mode 7); do not power-cycle the drive now...', flush=True)
    t = time.time()
    res = cam(C(0x3B, 0x07), timeout=180)
    print('  commit returned after %.1f s: %s' % (time.time() - t, 'GOOD' if res[0] else res[2]), flush=True)
    if not res[0]:
        print('  The commit reported an error. Do NOT power-cycle yet: run the dry run first and keep'
              ' the backup %s.' % backup)
        sys.exit(1)
    print('written. Power-cycle the drive, then run the dry run (without go): it must report 0 bytes differ.')


if __name__ == '__main__':
    main()
