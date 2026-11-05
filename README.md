# DROM6316 GD-ROM firmware

Firmware for the PHILIPS DVD-ROM DROM6316 (SATA, made by PBDS/BenQ, MediaTek MT1359) that reads
the whole Dreamcast GD-ROM, including the high-density area, and dumps normal CDs for Redump.
Based on ODNK. Current version: **DR05**. Tested on one drive, which had ODNK.

## Download

`DROM6316_DR05.bin`: https://archive.org/details/drom6316-dr05

SHA-256 `ace3e9b2a2273dd8b08b42f20aa3ac50909b126a1a70566f9ce9fca703097a02`

Changes against ODNK: [PATCHES.md](PATCHES.md).

## Flashing (Linux)

Tested on a native SATA (AHCI) port. Needs Python 3 and root. Put the image and `drom6316flash.py`
in one directory.

```
sudo python3 drom6316flash.py read backup.bin        # back up first
sudo python3 drom6316flash.py DROM6316_DR05.bin      # dry run: compares, sends nothing but reads
sudo python3 drom6316flash.py DROM6316_DR05.bin go   # flash
```

- The drive is found by its model; set `SGDEV=/dev/sgN` to pick it explicitly.
- `go` refuses an image for another drive or with a wrong checksum, saves the current flash to
  `drom6316flash-backup-<time>.bin`, uploads the image, reads it back from the drive and only then
  lets the drive write it. The write takes about 9 seconds. Do not power-cycle the drive while it runs.
- Afterwards power-cycle the drive (power off and on, not just a reboot of the computer) and run the
  dry run again: it must report 0 bytes differ, and the drive must report revision DR05.
- To go back, flash the backup with `go`.
- A disc may stay in the drive while flashing.

## Dumping

**GD-ROM**: [dcdump](https://github.com/scarabeeta/dcdump) knows the drive (DR05 and later). It runs
redumper for both areas with the settings below, splits the high-density area into tracks and
compares every track with redump:

```
dcdump --drive DROM6316 --ld-drive same
```

**By hand**, with [redumper](https://github.com/superg/redumper), which does not know the drive, so
its parameters are given on the command line. Normal CDs and the GD-ROM low-density area:

```
redumper disc --drive=/dev/srN --drive-type=GENERIC --drive-read-offset=6 --drive-c2-shift=0 \
  --drive-pregap-start=-135 --drive-read-method=BE --drive-sector-order=DATA_SUB_C2
```

GD-ROM high-density area (LBA 45000-549149), as one image (not split into tracks):

```
redumper dump --drive=/dev/srN --drive-type=GENERIC --drive-read-offset=6 --drive-c2-shift=0 \
  --drive-pregap-start=-135 --drive-read-method=BE --drive-sector-order=DATA_SUB_C2 \
  --speed=8 --lba-start=45000 --lba-end=549151
```

- `--speed=8` is required for the high-density area (see Known limits).
- `--lba-end=549151`, not 549150: with the disc's positive write offset the last sector needs one
  more sector of data.

## Known limits

- **Read GD-ROM high-density areas at 8x.** At the maximum speed the outer part of the HD area gives
  C2 errors and, worse, runs of sectors shifted by 186 samples **without any error report**. At 8x
  both disappeared (0 C2, 0 shifted sectors over whole discs).
- A single long seek from about 10 minutes to the outer edge of the HD area sometimes times out
  (3/02/00). Sequential dumping is not affected.
- DVD reading was not re-tested.

## Evidence

Dumps matching Redump, made with DR05:

1. Harusame Youbi (T-20106M, redump 27709): high-density track 3, one redumper pass, CRC/MD5 match.
2. Aero Dancing i (T-6807M, redump 43737): high-density tracks 3-5, one redumper pass, CRC/MD5 match.
3. Tekken 3 (Japan, Asia) (redump 588), CD: all 3 tracks match.

## License

Copyright (C) 2026 scarabeeta

`drom6316flash.py`, the documentation, and the changes to the firmware (listed in
[PATCHES.md](PATCHES.md)): GPL-3.0-or-later (see `LICENSE`). The rest of the firmware image belongs to
its rights holders and is not covered by this license.

## Disclaimer

Use at your own risk. I am not responsible for bricked drives or lost data.
