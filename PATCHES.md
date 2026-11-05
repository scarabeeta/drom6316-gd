# DR05 changes against ODNK

Base: PHILIPS DVD-ROM DROM6316 firmware **ODNK** (ODNK01). Only the main firmware (flash 0x8000-0x3FFFF)
changes; the drive never writes 0x0000-0x7FFF. 804 bytes differ.

Addresses: "common" = code 0x0000-0x67FF (file offset 0x8000 + address), "bankN" = banked code
0x6800-0xFFFF of bank N (file offset 0x8000 + N * 0x9800 + address).

The GD-ROM code paths first check that the disc's program area ends before frame 45150 (LBA 45000).
This holds for the LD area of every GD-ROM and not for normal CDs over 10 minutes, which keep the
original code.

## 1. Revision

- common 2274 (IDENTIFY, byte-swapped) and common 231A (INQUIRY): `ODNK` -> `DR05`.
- file 0x3FFFE: firmware checksum (16-bit sum of 0x8000-0x3FFFB).

## 2. Lead-out reads

The read range check (bank0 B09F) refused every sector from the lead-out on (5/21/00). Reads into the
lead-out are now allowed up to 512 sectors past its start, with the type of the last region.

- bank0 B246 -> F900: the last LBA of a request is compared with lead-out + 512.
- bank0 B1E7: the out-of-range jump for a request past the end of the region table goes to F9A0
  (section 3), then F940, which sets the last region's type and an end of lead-out + 513.

## 3. HD area range check

- bank0 F9A0: on a GD-ROM, a request from LBA 45000 on gets type "data" and an end frame of 600000
  (LBA 599850), then goes on to the original end check. Other requests go to F940 (section 2).
  Without this the HD area is refused as past the LD lead-out.

## 4. Seeks past minute 110

The firmware stops at minute 109. GD-ROM HD sectors go up to 122:04.

- bank2 CD2E: the seek entry refused a target minute > [XDATA 4C15] (110, also a servo parameter).
  Now compared with 122.
- bank3 F4BD: a target minute >= [4C15] was taken as a lead-in time, so the retry loop jumped back
  5 tracks every time the head got near 110:00. Now only minutes >= 123.
- common 6440 / 6540, bank3 C45F, C4F3, C506, C535: the two per-minute tables of the short-seek code
  have 110 entries, so minute 110 and later read into the next table. Both are copied to free space
  and extended to minute 122 (fitted on minutes 70-109); the four table bases point at the copies.

## 5. Reaching the start of the HD area

Between the LD lead-out and the HD area there is a band with no data, then the HD area's own
lead-in. Two checks sent the head the wrong way there.

- bank2 E1B1 -> F300: in the HD lead-in, Q gives only the time inside the lead-in (for example
  7:47). The firmware took that as the head position and jumped far outward. On a GD-ROM with a
  target in the HD area, a lead-in Q now sets the position to 10:01:00, just before the HD start.
- bank3 A34E -> FFA0: a long jump from the LD area lands in the LD lead-out (Q track AA, times up to
  about 8 minutes). The firmware took "in the lead-out, before the target" as past the end of the
  disc and stepped back 100 tracks at a time until the 6 s seek timeout. On a GD-ROM with a target in
  the HD area, this case now uses the normal distance calculation.
