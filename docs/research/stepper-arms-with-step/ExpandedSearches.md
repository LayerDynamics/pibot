# Expanded Searches — Open-Source Stepper Robot Arms with STEP (.step/.stp) CAD

**Research goal:** Surface, with concrete fetchable repo/file links, every open-source
**stepper-motor** robot arm that ships real **STEP** (B-rep `.step`/`.stp`) geometry —
NOT STL-only, NOT proprietary `.SLDPRT`-only. Servo arms (EEZYbotARM and similar) are
**out of scope**.

**Already found / cloned — find NEW ones beyond these:** Moveo, AR4, Faze4, Thor,
Arctos, AR3, PAROL6, SmallRobotArm, Open6X, AR2, Dummy-Robot, 6AR, Mirobot, RR1,
mariohany01 6-DOF, Martin-Ansteensen.

**Triage rule for downstream agents:** a hit only counts if (a) the motors are
**steppers** (NEMA17/NEMA23/NEMA8, integrated closed-loop steppers, etc.), and (b) a
real **STEP/STP** file is downloadable (a Files tab, a `CAD/` or `STEP/` folder, a
GrabCAD "Download → STEP" option). Reject STL-only kits, servo arms, and
SLDPRT/SLDASM-only drops with no neutral STEP export.

---

## Cluster 1 — GitHub repos shipping STEP for stepper arms (topics + code search)

**Why it matters:** GitHub is the densest source of fully open builds, and many ship a
`CAD/`, `STEP/`, or `hardware/` folder with neutral geometry. Topic pages plus
extension-scoped code search catch arms that never make it onto curated lists.

- `https://github.com/topics/robot-arm`
- `https://github.com/topics/robotic-arm`
- `https://github.com/topics/6dof` and `https://github.com/topics/6-dof-robot-arm`
- `https://github.com/topics/stepper-motor robot arm`
- robot arm stepper nema17 site:github.com
- "robot arm" "step file" stepper site:github.com
- extension:step robot arm stepper (GitHub code search)
- extension:stp "robot arm" nema17 (GitHub code search)
- path:CAD extension:step robot arm (GitHub code search)
- filename:*.step robot arm 6 axis stepper (GitHub code search)
- "NEMA 23" OR "NEMA 17" 6-axis arm "STEP" site:github.com

## Cluster 2 — Hackaday.io stepper robot-arm projects with STEP in Files

**Why it matters:** Hackaday.io hosts many independent stepper-arm builds whose CAD lives
only in the project's **Files** tab (often a zipped STEP), invisible to GitHub-only
sweeps.

- site:hackaday.io robot arm stepper STEP
- site:hackaday.io "robotic arm" nema17 "step file"
- site:hackaday.io 6 axis robot arm STEP download
- site:hackaday.io desktop robot arm stepper CAD
- site:hackaday.io "harmonic drive" robot arm stepper STEP
- robot arm hackaday.io stepper "step files" Files tab
- site:hackaday.io DIY 6 DOF arm nema23 STEP

## Cluster 3 — GrabCAD stepper robot arm models with STEP downloads

**Why it matters:** GrabCAD is the largest neutral-CAD library; many entries explicitly
offer a STEP download even when the source design was SolidWorks. Filter hard for
**stepper** actuation and a STEP (not just rendered/STL) download.

- site:grabcad.com robot arm stepper STEP
- site:grabcad.com "6 axis" robotic arm nema17 step
- site:grabcad.com robotic arm "step" download stepper motor
- site:grabcad.com desktop 6 dof arm STEP stepper
- site:grabcad.com SCARA stepper arm step file
- site:grabcad.com "robot arm" "nema 23" step
- grabcad robotic arm stepper neutral CAD step download

## Cluster 4 — Printables / Thingiverse / MyMiniFactory stepper arms WITH STEP

**Why it matters:** Print sites are STL-dominated, so the win is the rare entry that also
attaches a STEP — these are easy to miss and exactly in scope. Must verify a STEP exists,
not just STL.

- site:printables.com robot arm stepper "step" file nema17
- site:printables.com 6 dof arm STEP download stepper
- site:thingiverse.com robot arm stepper step file (not just stl)
- site:thingiverse.com "6 axis" robotic arm nema17 STEP
- site:myminifactory.com robot arm stepper STEP CAD
- printables robotic arm nema23 "step" source files
- thingiverse robot arm stepper "step" "stp" cad

## Cluster 5 — Instructables / university / blog builds linking STEP

**Why it matters:** Build writeups (Instructables, .edu capstones, maker blogs) frequently
host the real CAD off-platform (Google Drive, OneDrive, a course page) and are absent from
both GitHub topics and CAD libraries.

- site:instructables.com robot arm stepper STEP file 6 axis
- site:instructables.com nema17 robotic arm "step" cad download
- robot arm stepper "step file" capstone site:edu
- "robotic arm" stepper STEP CAD download university project
- 6-axis stepper robot arm build blog "step files" download
- maker robot arm nema23 STEP "google drive" download
- DIY industrial robot arm stepper STEP "onedrive" OR "dropbox"

## Cluster 6 — Curated lists to mine for STEP-having stepper arms

**Why it matters:** Awesome-style and collected lists already aggregate dozens of arms;
mining them and then checking each candidate's repo for a STEP folder is the
highest-yield way to find lesser-known stepper arms fast.

- awesome-open-source-robotic-arms site:github.com
- hobofan/collected-robotic-arms (read the README, follow every arm link)
- "awesome robot arm" OR "awesome robotic arm" open source list github
- open source robot arm list stepper STEP github README
- collected robotic arms list nema17 stepper STEP CAD
- reddit r/robotics "open source" stepper arm "step file" list
- "list of open source robot arms" stepper CAD STEP

## Cluster 7 — Specific lesser-known / named stepper arms likely to ship STEP

**Why it matters:** Several stepper arms are known by a product or codename rather than a
topic tag; querying the names directly with "STEP" flushes out their CAD even when the
landing page buries it. Includes BCN3D/Annin-style clones that often re-share STEP.

- "BCN3D MOVEO" STEP stp original CAD download (find non-STL forks with STEP)
- "Annin" OR "AR4" style clone robot arm STEP github stepper
- "desktop robot arm" stepper STEP download
- "DIY 6 axis robot arm" STEP file nema17
- "Robot Arm" stepper "step" "stp" -stl github 6dof
- WLkata OR "Mirobot" clone open source stepper STEP
- "robotic arm" stepper "harmonic" OR "cycloidal" STEP github
- "closed loop stepper" robot arm STEP CAD download
- igus OR "BLDC" excluded — verify motors are steppers, then capture STEP link

## Cluster 8 — Cycloidal / harmonic-drive stepper actuator arms with STEP

**Why it matters:** A distinct sub-genre of high-end DIY arms uses stepper-driven
cycloidal or strain-wave (harmonic) joints and almost always publishes STEP for the gear
geometry — a rich, in-scope vein the generic queries under-cover.

- cycloidal robot arm stepper STEP github nema17
- "strain wave" OR "harmonic drive" robot arm stepper STEP download
- 3d printed cycloidal actuator robot arm STEP stp github
- robot arm stepper cycloidal gear "step" CAD site:github.com
- site:hackaday.io cycloidal robot arm stepper STEP files
- "robot joint" stepper cycloidal STEP CAD open source

## Cluster 9 — Stepper SCARA & delta/desktop arms with STEP

**Why it matters:** SCARA and desktop/educational stepper arms are common, frequently
ship neutral CAD, and are easy to overlook when queries focus on 6-DOF vertical
articulated arms. In scope as long as motors are steppers and STEP is provided.

- open source SCARA robot arm stepper STEP github
- site:grabcad.com SCARA stepper arm STEP download
- "RobotDigg" OR "MakerArm" SCARA stepper STEP CAD
- desktop educational robot arm stepper STEP file github
- 4-axis SCARA nema17 stepper "step" CAD download
- site:hackaday.io SCARA stepper arm STEP files
