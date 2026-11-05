# DR05 changes against ODNK

Base: PHILIPS DVD-ROM DROM6316 firmware **ODNK** (ODNK01). Only the main firmware (flash 0x8000-0x3FFFF) is
changed; the boot block and the drive's own data at 0x0000-0x7FFF are never written by the drive.
804 bytes differ. Addresses: "common" = code 0x0000-0x67FF (file offset 0x8000 + address), "bankN" =
banked code 0x6800-0xFFFF of bank N (file offset 0x8000 + N * 0x9800 + address).

Every new code path that is specific to GD-ROM checks first that the disc's program area ends before
frame 45150 (LBA 45000, where the GD high-density area starts). This is true for every GD-ROM's
low-density area and false for normal CDs over 10 minutes, so normal CDs run the original code.

## 1. Revision

- common 2274 (IDENTIFY, byte-swapped) and common 231A (INQUIRY): `ODNK` -> `DR05`.
- file 0x3FFFE: firmware checksum (16-bit sum of 0x8000-0x3FFFB) recomputed.

## 2. Lead-out reads

The read range check (bank0 B09F) refused every sector at or past the lead-out (5/21/00). Requests
that run into the lead-out are now allowed for 512 sectors past the lead-out start, with the type of
the last region (data or audio).

- bank0 B246 -> F900: last LBA of a request that spans into the lead-out is compared with the
  lead-out + 512 instead of the lead-out.
- bank0 B1E7: the jump to the out-of-range exit, taken when a request runs past the end of the region
  table, now goes to F9A0 (section 3) and from there to F940. F940 gives the request the last
  region's type and an end of lead-out + 513.

## 3. GD-ROM high-density area: range check

- bank0 F9A0: on a GD-ROM, a request starting at LBA 45000 or later gets region type "data" with an
  end frame of 600000 (LBA 599850), then continues with the original request-end check. Other
  requests continue at F940 (section 2). Without this the HD area is refused like any LBA past the
  low-density lead-out.

## 4. Seeking past minute 110

The firmware assumed a disc never goes past minute 109. GD-ROM HD sectors go up to 122:04.

- bank2 CD2E: the seek entry refused a target minute > [XDATA 4C15] (= 110, also a servo
  parameter). Now compared with the constant 122.
- bank3 F4BD: a target minute >= [4C15] was treated as a lead-in time "behind" the head, so the
  retry loop jumped back 5 tracks every time the head neared 110:00. Now only minutes >= 123.
- common 6440 / 6540, bank3 C45F, C4F3, C506, C535: the two per-minute tables of the short-seek
  code had 110 entries (minutes 0-109); minute 110 and later read the next table. Both are copied to
  free space and extended to minute 122 (curve fitted on minutes 70-109); the four table base
  addresses point at the copies.

## 5. Reaching the start of the GD-ROM high-density area

Between the low-density lead-out and the HD area there is a band with no data, followed by the HD
area's own lead-in. Two decisions sent the head the wrong way there.

- bank2 E1B1 -> F300: when the head lands in the HD lead-in, the Q channel carries only the time
  inside the lead-in (for example 7:47). The firmware took that as the head position and jumped far
  outward. On a GD-ROM with a target in the HD area, a lead-in Q now sets the position to 10:01:00,
  just before the HD start.
- bank3 A34E -> FFA0: a long jump from the low-density area lands in the GD-ROM's long low-density
  lead-out (Q track AA, times up to about 8 minutes). The firmware read "in the lead-out but before
  the target" as "past the end of the disc" and went back 100 tracks at a time, again and again,
  until the 6 s seek timeout. On a GD-ROM with a target in the HD area, this case now uses the normal
  distance calculation and keeps going outward.
