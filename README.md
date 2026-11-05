# DROM6316 GD-ROM firmware

PHILIPS DVD-ROM DROM6316 (SATA, PBDS/BenQ, MediaTek MT1359) firmware for dumping the high-density
area of Dreamcast GD-ROMs. Based on ODNK. Current version: **DR05**.

## Download

`DROM6316_DR05.bin`: https://archive.org/details/drom6316-dr05

SHA-256 `ace3e9b2a2273dd8b08b42f20aa3ac50909b126a1a70566f9ce9fca703097a02`

Changes against ODNK: [PATCHES.md](PATCHES.md).

## Flashing (Linux)

Native SATA port. Needs Python 3 and root. Put the image and `drom6316flash.py` in one directory.

```
sudo python3 drom6316flash.py read backup.bin        # back up first
sudo python3 drom6316flash.py DROM6316_DR05.bin      # dry run
sudo python3 drom6316flash.py DROM6316_DR05.bin go   # flash
```

- The drive is found by its model. `SGDEV=/dev/sgN` picks one explicitly.
- `go` saves the current flash to `drom6316flash-backup-<time>.bin` first. The write takes about
  9 seconds; do not power off the drive during it.
- Then power-cycle the drive and run the dry run again. It should report 0 bytes differ.
- To go back, flash the backup with `go`.
- The disc can stay in the drive.

## Dumping

With [dcdump](https://github.com/scarabeeta/dcdump):

```
dcdump --drive DROM6316
```

dcdump reads the LD area on a drive from Redump's CD list, then the HD area on the DROM6316.

By hand, HD area with redumper at 8x:

```
redumper dump --drive=/dev/srN --drive-type=GENERIC --drive-read-offset=6 --drive-c2-shift=0 \
  --drive-pregap-start=-135 --drive-read-method=BE --drive-sector-order=DATA_SUB_C2 \
  --speed=8 --lba-start=45000 --lba-end=549151
```

This gives one image of the HD area, not split into tracks. The end is 549151, one past the last
sector, because of the disc's write offset.

## Known limits

- Tested on one drive.
- Read the HD area at 8x. At full speed the outer part gives C2 errors, and some sectors come back
  shifted by 186 samples with no error reported.
- A single long seek from around minute 10 to the outer edge sometimes times out (3/02/00).
  Sequential reads are fine.
- DVD reading not tested.

## Evidence

HD tracks matching Redump, DR05 at 8x:

1. Harusame Youbi (T-20106M): track 3.
2. Aero Dancing i (T-6807M): tracks 3-5.

## License

Copyright (C) 2026 scarabeeta

`drom6316flash.py`, the documentation, and the changes to the firmware (listed in
[PATCHES.md](PATCHES.md)): GPL-3.0-or-later (see `LICENSE`). The rest of the firmware image belongs to
its rights holders and is not covered by this license.

## Disclaimer

Use at your own risk. I am not responsible for bricked drives or lost data.
