# Train / test overlap check

Compared 3642 training source images (old deployed training set data/train/HR: 192, DIV2K train: 800, Flickr2K: 2650) against 161 test and validation images (Set5, Set14, BSD100, and the 42 DIV2K validation images).

* expected: 12 held-out images of the deployed model's old validation set (data/train/HR #181-192) are part of val42 on purpose and are in NO training set (the new store excludes them by md5)
* exact pixel match (incl. flips/rotations), unexpected: **0**
* whole-image near duplicate (thumbnail correlation > 0.95, 8 dihedral variants): **0**
* contained as a region (template matching at 1/8 scale, score > 0.97): **0**

Closest candidates (highest scores found; below the thresholds they are different images):

| test | training image | thumbnail corr. |
|---|---|---|
| val42/0846.png | flickr2k/000297.png | 0.914 |
| BSD100/167062 | flickr2k/002535.png | 0.899 |
| val42/0846.png | div2k_train/636 | 0.889 |
| BSD100/167062 | flickr2k/001688.png | 0.888 |
| BSD100/167062 | flickr2k/000375.png | 0.886 |

| test | training image | template score |
|---|---|---|
| BSD100/167062 | flickr2k/001770.png | 0.968 |
| BSD100/167062 | flickr2k/001405.png | 0.965 |
| BSD100/167062 | flickr2k/000253.png | 0.964 |
| BSD100/167062 | old_trained/img0341.png | 0.962 |
| BSD100/167062 | flickr2k/000522.png | 0.962 |

Hits above threshold (empty = none):


Limits: crops that were also rotated or resized by an arbitrary factor are not found by the template test; the store crops are not searched directly (they are cut from the source images compared here). Saved by software/ai/dataset/check_overlap.py.
