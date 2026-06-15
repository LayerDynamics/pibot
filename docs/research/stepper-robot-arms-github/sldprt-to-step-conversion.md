# Converting SolidWorks `.SLDPRT` / `.SLDASM` to STEP (BREP) — without SolidWorks, on macOS

**Date:** 2026-06-15
**Situation:** 87 `.SLDPRT` parts + 23 `.SLDASM` assemblies from the **BCN3D Moveo**
open-source robot arm (MIT-licensed, fully public, real binary SolidWorks files —
**SolidWorks 2013** version). Host = macOS / Apple Silicon. No SolidWorks. `assimp`
installed; FreeCAD not installed but available via `brew install --cask freecad` (1.1.1).
Goal = **STEP with B-Rep / parametric-ish solids, NOT mesh**. Public files → cloud upload
is acceptable confidentiality-wise.

---

## TL;DR

- **FreeCAD does NOT read `.SLDPRT` / `.SLDASM` natively** (proprietary, closed format —
  Dassault won't license it). The only FreeCAD "addon" path wraps the **paid, now
  sale-suspended** CAD Exchanger. FreeCAD is **downstream** of conversion: you get a STEP
  some other way, *then* import it into FreeCAD. Not a solution to the conversion itself.
- **There is NO free, fully-local, scriptable open-source path that produces B-Rep STEP
  from native `.SLDPRT`.** The format is proprietary; no OSS reader extracts the Parasolid
  B-Rep. Anyone telling you otherwise is conflating mesh extraction (STL) or BOM/metadata
  parsing with real solid-geometry export. `assimp` (the one installed tool) is **mesh-only
  and cannot read `.SLDPRT` at all** — it is irrelevant here.
- **Best executable method for THIS case (110 public files, macOS, free, B-Rep, handles
  assemblies):** **Onshape Free plan in the browser.** It natively imports `.SLDPRT` and a
  **Pack-and-Go ZIP** of each `.SLDASM` (top-level assembly + all child parts in one zip),
  and exports a single **STEP with real B-Rep** per part/assembly. Free, runs on Apple
  Silicon via browser, handles assembly reference resolution. **Caveat: it is manual/GUI,
  not scriptable** on the free plan (free-plan API is restricted and forbids automated use),
  and **all documents must be public** (fine — these files are already public MIT).
- **If you want one scripted batch pass on macOS, the only real options are PAID:**
  **Datakit CrossManager CLI** (reads `.SLDPRT`/`.SLDASM`, writes STEP, headless CLI on
  macOS) or **CAD Exchanger Batch CLI** (same, but general sale currently suspended).
  Both are perpetual/annual commercial licenses, no published price.
- **Version is not a problem:** the Moveo files are **SolidWorks 2013**, old enough that
  every modern reader (Onshape, CrossManager, CAD Exchanger) handles them. The "fails on
  very new SLDPRT" risk applies to current-year files, not these.

---

## 1. Can FreeCAD (1.1, 2025/2026) import `.SLDPRT`? — **NO**

Definitive: **No.** FreeCAD cannot open native SolidWorks `.SLDPRT` or `.SLDASM`. The format
is proprietary with a closed specification; Dassault does not license a reader, so FreeCAD
ships none. The official/community guidance is to first convert SolidWorks files to a neutral
format (STEP/IGES) and import *that* into FreeCAD.

- The only FreeCAD-based path is **yorikvanhavre/CADExchanger**, an addon that shells out to
  the **commercial CAD Exchanger** binary to do the read. That is not "FreeCAD reading
  SLDPRT" — it is the paid CAD Exchanger reading it, and CAD Exchanger's general sale is
  **currently suspended** (see §2). So there is **no free FreeCAD path**.
- **Conclusion:** FreeCAD's role here is purely *after* conversion — open/inspect/edit the
  resulting STEP. Don't `brew install freecad` expecting it to convert these files; it can't.

Sources: FreeCAD forum "Import SolidWorks (sldprt) to FreeCAD"; CanadaCAD "Free CAD Software
Compatible with SolidWorks"; ACS CAD Services "How to Open SLDPRT Without SolidWorks";
yorikvanhavre/CADExchanger GitHub.

---

## 2. Tools that actually read native `.SLDPRT` and export STEP (no SolidWorks)

| Tool | Reads native SLDPRT? | Output: **B-Rep** STEP? | macOS? | CLI / batch / API? | Cost / license |
|---|---|---|---|---|---|
| **Onshape (Free)** | **Yes** (native import) | **Yes — B-Rep** | Yes (browser, Apple Silicon) | **GUI only on free**; REST API exists but **restricted on free plan, no automated/scrape use** | **Free** (docs public, non-commercial) |
| **Datakit CrossManager CLI** | **Yes** (`.SLDPRT`+`.SLDASM`) | **Yes — B-Rep** | **Yes** (Win/Linux/**macOS**, headless) | **Yes — scriptable batch CLI** | **Paid**, perpetual/annual, no public price |
| **CAD Exchanger Batch (CLI)** | **Yes** | **Yes — B-Rep** | **Yes** (Win/Linux/macOS) | **Yes — batch CLI** (`ExchangerConv`) | **Paid**; *general sale currently suspended* (Lab GUI ~$590–$2,690) |
| **CAD Exchanger Lab (GUI)** | **Yes** | **Yes — B-Rep** | Yes | GUI only (free *trial*) | Paid (free trial only); sale suspended |
| **Fusion 360** | Yes (upload SLDPRT) | Yes — B-Rep export STEP | Yes (desktop) | No public file-convert API for this; GUI | Free for personal/hobby (gated), else paid |
| **CloudConvert (API)** | **No** | — | n/a | API exists | CAD support = DWG/DXF/PDF only; **no SLDPRT/STEP** |
| **AnyConv / fabconvert / convert3d / convert.guru** | "Yes" (online) | **Likely MESH-in-STEP, not B-Rep** ⚠ | n/a | per-file web only | Free but per-file, tessellated output suspected |
| **ConvertCADFiles.com** | Yes | Mixed | n/a | per-file web | Free tier = **1 file, ≤50 KB** → useless for real parts |
| **3DPEA** | Views SLDPRT; "BREP→STEP" is separate | Unverified for SLDPRT→STEP B-Rep | n/a | per-file web | Free, per-file |
| **`assimp` (installed)** | **No** (mesh formats only) | — | Yes | CLI | Free OSS — **irrelevant, can't read SLDPRT** |
| **OSS "libsldprt"-type readers** | Parse structure/**BOM/metadata** only | **No B-Rep export** | varies | varies | Free OSS — **does not produce solid-geometry STEP** |

Notes / verifications:

- **Native SLDPRT contains Parasolid B-Rep.** A *real* reader (Onshape, CrossManager, CAD
  Exchanger) extracts that B-Rep → genuine solid STEP. A *tessellator* (most free online
  "converters", eDrawings→STL) emits triangles. The user's "no mesh" rule **disqualifies any
  tool that wraps a mesh in a `.step` container** — verify per-tool before trusting it.
- **CAD Exchanger sale is suspended.** CAD Interop's own page: *"the sale of CAD Exchanger is
  temporarily suspended … we suggest 3DViewStation as an equivalent alternative."* A free
  **trial** of Lab is still downloadable, but you can't buy the Batch CLI right now.
- **CloudConvert does NOT support SLDPRT or STEP** — its CAD category is DWG/DXF/PDF only.
  Rule it out entirely.
- **GrabCAD Workbench** (which used to convert SLDPRT→STEP on upload) **no longer exists** as
  a usable service. GrabCAD tutorials now just tell you to use SolidWorks or eDrawings→STL
  (mesh). Rule it out.
- **No genuine open-source SLDPRT→B-Rep exporter exists.** The "C++20 toolkit that reads
  SLDPRT with a BREP parser" that surfaced in one search was **not corroborated by a real
  repository** (the `github.com/sldprt` org is unrelated forks). Treat OSS SLDPRT tooling as
  BOM/metadata/structure parsing only — **not** solid-geometry conversion.

---

## 3. Batch / automation for all 110 files in one scripted pass on macOS

**Honest answer: the only *free* option (Onshape) is manual/GUI — it cannot do one scripted
pass.** A single scripted batch on macOS exists **only with a paid CLI**:

- **Datakit CrossManager CLI** — headless, macOS-supported, reads `.SLDPRT`/`.SLDASM`, writes
  STEP. Designed exactly for "tight integration into your workflow (PLM, background services,
  scripts)." Drop all files in a folder and loop the CLI over them. **Paid.**
- **CAD Exchanger Batch (`ExchangerConv`)** — macOS CLI; on macOS you open a terminal at
  `Contents/MacOS/` and run `ExchangerConv <in> <out>`. Scriptable over 110 files. **Paid,
  sale suspended.**

So: **if budget = $0, there is no one-command batch pass — Onshape is per-file/per-assembly
manual import+export in the browser** (still very doable for 110 files, just clicky). If
budget opens up, CrossManager CLI is the clean scripted answer.

---

## 4. The assembly problem (`.SLDASM` → child `.SLDPRT`)

The 23 `.SLDASM` reference child `.SLDPRT`. Reference resolution is the discriminator:

- **Onshape:** **handles it correctly** via **Pack and Go** — zip the top-level `.SLDASM`
  with all its child parts (flattened to one folder, same name as the assembly), import the
  ZIP, and Onshape rebuilds the assembly with references resolved. Export → one STEP with all
  solids. This is the recommended SolidWorks→Onshape migration path. **This also means you
  may not need 110 separate conversions** — import each assembly zip once and export one
  assembly STEP that contains its parts.
- **Datakit CrossManager / CAD Exchanger:** resolve assembly references **when all referenced
  `.SLDPRT` are present in the folder** alongside the `.SLDASM`. They produce a single
  multi-solid STEP. (The Moveo repo ships the parts next to the assemblies, so this works.)
- **Per-file online converters (AnyConv, ConvertCADFiles, 3DPEA, etc.): BREAK on
  assemblies.** You upload one `.SLDASM`, the child parts aren't uploaded with it, so geometry
  is missing/empty. They are part-only tools. **Do not use them for the `.SLDASM` files.**

---

## 5. SolidWorks version constraint

Relevant in general — some converters choke on **very new** (current-year) `.SLDPRT`
versions because the reader hasn't been updated for the latest file schema. **Not a problem
here:** the BCN3D Moveo CAD files are **SolidWorks 2013** vintage, comfortably within range of
every current reader (Onshape, CrossManager, CAD Exchanger). No version risk for this dataset.

---

## RANKED RECOMMENDATION (best → worst for THIS case)

Preference order given: **free > local > scriptable > GUI > cloud > paid.** Because no free
*local/scriptable* B-Rep path exists, a **free cloud GUI** tool (Onshape) outranks every paid
local CLI.

1. **Onshape Free (browser)** — ✅ free, ✅ B-Rep STEP, ✅ resolves assemblies (Pack-and-Go
   zip), ✅ Apple Silicon. ❌ manual/GUI (no free-plan automation), ❌ docs must be public
   (OK — files are public MIT). **Top pick.**
2. **Datakit CrossManager CLI** — ✅ macOS, ✅ B-Rep, ✅ `.SLDPRT`+`.SLDASM`, ✅ **scriptable
   one-pass batch**. ❌ paid. *The pick if you want automation and have budget.*
3. **CAD Exchanger Batch CLI** — same strengths as #2, but **general sale suspended** → can't
   purchase now. Free Lab *trial* (GUI) is the only currently-obtainable slice.
4. **Fusion 360 (free personal)** — opens SLDPRT, exports B-Rep STEP, but GUI/per-file and
   personal-license-gated; clunkier than Onshape for 110 files + assemblies.
5. **Per-file online converters (AnyConv / ConvertCADFiles / 3DPEA / convert3d / etc.)** —
   ⚠ likely **mesh-in-STEP**, ⚠ **break on assemblies**, ⚠ tiny free-size caps
   (ConvertCADFiles = 1 file ≤50 KB). **Violate the "no mesh" requirement — avoid.**
6. **FreeCAD / assimp / OSS** — **cannot read SLDPRT.** Not options for the conversion step.
   FreeCAD is only useful *after* (open the STEP you produced).

### Top-pick concrete steps (Onshape Free, macOS)

1. Create a free Onshape account at <https://www.onshape.com/en/products/free> (free plan =
   public documents, non-commercial — fine for the public MIT Moveo files).
2. **For the 23 assemblies:** build a **Pack-and-Go-style ZIP per `.SLDASM`** — put the
   `.SLDASM` plus all its child `.SLDPRT` in one flat folder named after the assembly, and zip
   it. (The Moveo repo keeps parts alongside assemblies, so gather each assembly's parts.)
3. In Onshape: **Create document → Import** the ZIP (for assemblies) or the individual
   `.SLDPRT` (for standalone parts). Onshape resolves references and builds the model.
4. Right-click the Part Studio / Assembly tab → **Export → STEP** (AP242 or AP214) →
   download. This STEP is **B-Rep solids**, not mesh.
5. Repeat per part/assembly. (No free-plan scripting — it's click-through, but 110 imports is
   tractable; assemblies collapse many parts into one export each.)
6. Open the resulting `.step` in FreeCAD (`brew install --cask freecad`) if you need to
   inspect/edit them locally afterward.

> If this becomes too tedious or you need it reproducible/scripted: buy **Datakit
> CrossManager CLI**, drop all files in a folder, and loop the CLI to emit STEP for every part
> and assembly in one pass on macOS. That is the only realistic *scripted* route and it is
> paid.

---

## Sources

- FreeCAD forum — "Import SolidWorks (sldprt) to FreeCAD": <https://forum.freecad.org/viewtopic.php?style=4&t=603&start=20>
- CanadaCAD — "Free CAD Software Compatible with SolidWorks": <https://www.canadacad.ca/free-cad-software-compatible-with-solidworks/>
- ACS CAD Services — "How to Open SLDPRT Files Without SolidWorks (Free Methods)": <https://acscadservices.com/how-to-open-sldprt-files-without-solidworks/>
- yorikvanhavre/CADExchanger (FreeCAD addon wrapping paid CAD Exchanger): <https://github.com/yorikvanhavre/CADExchanger>
- CAD Exchanger — Lab product page: <https://cadexchanger.com/products/gui/>
- CAD Exchanger — SLDPRT to STEP: <https://cadexchanger.com/sldprt-to-step/>
- CAD Exchanger — SLDPRT format page: <https://cadexchanger.com/sldprt/>
- CAD Exchanger Batch CLI — launching docs: <https://docs.cadexchanger.com/cli/launching>
- CAD Interop — "Which CAD Exchanger license is right for you" (notes sale suspended): <https://www.cadinterop.com/en/our-products/cad-exchanger-software/which-cad-exchanger-license-is-right-for-you.html>
- Datakit — "Product Focus: CrossManager CLI": <https://www.datakit.com/en/news/product-focus-crossmanager-cli-241.html>
- Datakit — SOLIDWORKS 3D to STEP convertor: <https://www.datakit.com/cad-convertors/solidworks-3d-to-step/3-7-1.html>
- Onshape — "Strategies for Migrating SOLIDWORKS Data" (Pack and Go): <https://www.onshape.com/en/resource-center/tech-tips/strategies-migrating-solidworks-data>
- Onshape — Importing Files help: <https://cad.onshape.com/help/Content/Document/importing_files.htm>
- Onshape — Exporting Files help (STEP/Parasolid/etc.): <https://cad.onshape.com/help/Content/File/exporting_files.htm>
- Onshape forum — "Export in free version?": <https://forum.onshape.com/discussion/10703/export-in-free-version>
- Onshape — Free plan / API limits discussion: <https://forum.onshape.com/discussion/29034/new-onshape-api-limits>
- CloudConvert — CAD converter (DWG/DXF/PDF only): <https://cloudconvert.com/cad-converter>
- ConvertCADFiles.com (free tier limits): <https://convertcadfiles.com/>
- 3DPEA — BREP to STEP: <https://www.3dpea.com/en/convert/BREP-to-STEP>
- AnyConv — SLDPRT converter: <https://anyconv.com/sldprt-converter/>
- GrabCAD tutorial — "How do I convert .SLDPRT to .STEP?": <https://grabcad.com/tutorials/how-do-i-convert-sldprt-to-step>
- BCN3D-Moveo GitHub (CAD files, SolidWorks 2013): <https://github.com/BCN3D/BCN3D-Moveo>
