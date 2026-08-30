# bug_log — section_geometry

↑ [`docs index`](README.md) · [`section_geometry`](../README.md)

## Role

Worker debug log for this package. Each entry records the **symptom** as
observed, the **evidence** that pinned it, the **root cause**, and — once
fixed — the **verification**. Entries stay in the log after they close, per
[`DOCUMENTATION_STANDARDS`](../../../../../docs/conventions/documentation/DOCUMENTATION_STANDARDS.md);
superseded conclusions are struck through or narrated rather than deleted,
because several of these were mis-attributed on first pass and the correction is
the useful part.

**Identifiers.** Entries here are `SG-nnn`, local to this package. `BL-nnn`
refers to the repo-root [`docs/bug_log.md`](../../../../../docs/bug_log.md),
which tracks the section-selection sizing chain; the two numbering spaces are
independent.

**Reference case throughout:** NACA 2412, 1.0 m chord, 200 airfoil points,
6 mm skin / 14 mm spar cap / 8 mm shear web, layouts named by the
[system-type taxonomy](reference/system_type_xyz_taxonomy.md) (`2D-F`, `5D-CN`, …).
Deviations are stated per entry.

## Index

| ID | Title | Status |
|---|---|---|
| [SG-001](#sg-001) | Box-cap (family **D**) midline loses its curvature during topology preparation | **Fixed** (twice — the first fix was a better guess and was superseded) |
| [SG-002](#sg-002) | Shear-web midline kinks at the foot during junction preparation | **Fixed** at the root (emit extent) |
| [SG-003](#sg-003) | Band-cap (**B**) and discrete-cap (**C**) ends are relocated onto the skin | **Fixed** (no relocation at all) |
| [SG-004](#sg-004) | Cap–web junction has no shared node at a cap **end** | **Fixed** at emit |
| [SG-005](#sg-005) | Interior cap–web T-junctions have a node on the **cap** side only | **Open** — latent, conforms on mesher tolerance |
| [SG-006](#sg-006) | `centerline_mesh` still draws the bounding-box filter SG-001 deleted | **Open** — figure only, no effect on geometry or mesh |

## Standing invariant (established 2026-08-30)

**A component must emit its mid-surface at its true extent, so junctions
coincide by construction. Topology splits and indexes; it never relocates.**

SG-001 through SG-004 were one failure of this: a strip emitted short or in the
wrong place forces the topology pass to move it, moving it requires guessing a
direction or a tolerance, and each guess is a bug waiting to happen. The
heuristics that exist only to support relocation are the surface area for that
class of bug. Status after applying the invariant to both paths:

| Heuristic | Was | Now |
|---|---|---|
| web foot ← `point_to_open_polyline_nearest` | relocated the foot | **relocation gone** — web emits to the skin mid-surface; the call survives in `split_skin_at_junctions` but only to read an arc length |
| cap end ← `point_to_open_polyline_nearest` + `_CAP_ENDPOINT_ON_WEB_TOL_M` | relocated free ends onto the skin | **gone** — caps pass through `skin_split` untouched, and the constant and its last consumer have since been deleted (SG-004) |
| cap **end** ↔ web node ← mesher `ENDPOINT_TOL_FRAC` (6 mm at 1 m chord) | junction conformed on ~4 mm of margin | **gone** — web emits a vertex at each cap-end junction, coincident to 0.000 µm |
| cap **interior** ↔ web node ← mesher `ENDPOINT_TOL_FRAC` | junction conformed on ~4 mm of margin | **still there** — SG-005 |
| cap resample ← `_SKIN_RAY_CAP_BBOX_MARGIN_M` | proximity box with a fixed margin | **gone from the geometry path** — skin vertices selected by declared suction/pressure side; the constant survives for one plot (SG-006) |

The merge tolerance that decides when two skin cuts are one cut is *indexing*,
not relocation, so it stays — but it is now derived from the arc being split
(`_MERGE_S_TOL_FRAC` × half-ring length) instead of being absolute. It was the
only tolerance in the junction path that did not scale: headroom against the
minimum web spacing (`min_web_gap_frac`, 2 % of chord) fell 200x → 48x → 10x
from a 1.0 m to a 0.05 m chord, and is now constant at ~200x. Behaviour at the
1 m reference chord is unchanged (99.93 µm vs the old fixed 100 µm).

### What a grep still finds (verified 2026-08-30, after cleanup)

The tables above are about *relocation*, not about whether a symbol appears.
This section covers the **whole package plus its downstream callers**, including
`tests/` and `visualisation/` — unlike the tolerance audit below, which excludes
them. Nothing in this list is a defect except where noted, so do not "clean
them up" without reading the linked entry first.

`point_to_open_polyline_nearest` — 5 live sites:

| Site | Still there because |
|---|---|
| `midlines/ring_geometry.py` | definition. |
| `midlines/skin_split.py`, in `split_skin_at_junctions` | **indexing only.** The web foot is already the junction; this reads the arc length at which to split the skin. It no longer writes to `arr[row]`. See SG-002. |
| `topology/shell_strip_topology.py` | re-export plus a `_point_to_open_polyline_nearest` compatibility alias. No call. |
| `visualisation/demos/shell_junction_topology_demo.py`, `visualisation/demos/topology_twist_stability_demo.py` | **measurement.** Both demos use it to *report* junction gaps, which is what produced the numbers in SG-002 and SG-005. |
| `mesh_utilities/section_mesh/visualisation/centerline_mesh.py` | plotting — and part of SG-006. |

It is **gone** from `topology/cap_web_junctions.py`, which no longer imports it.

`_SKIN_RAY_CAP_BBOX_MARGIN_M` — 3 live sites, all outside the geometry path:

| Site | Still there because |
|---|---|
| `midlines/cap_skin_ray_resample.py` | definition, documented as unused by the resampler. |
| `topology/shell_strip_topology.py` | re-export in `__all__` **only** so `centerline_mesh` can import it through this module. The inert `ShellStripTopologySpec.skin_ray_cap_bbox_margin_m` field that used to default from it has been deleted (SG-001). |
| `mesh_utilities/section_mesh/visualisation/centerline_mesh.py` | it still implements the deleted filter — SG-006. |

Deleted during the 2026-08-30 cleanup, 0 references each: `_CAP_ENDPOINT_ON_WEB_TOL_M`,
`_MERGE_S_TOL_M`, `_axis_polyline_crossing_nearest`, `required_cap_bbox_margin_m`,
`_SKIN_RAY_BBOX_MARGIN_SAFETY`, `ShellStripTopologySpec.skin_ray_cap_bbox_margin_m`,
and the `skin_ray_cap_bbox_margin_m` parameter of `shell_mesh_inputs_from_section`.

**Still open:** SG-005 (geometry) and SG-006 (a figure).

SG-001 through SG-004 were all found while building
[`visualisation/demos/geometry_to_mesh_flythrough.py`](../visualisation/demos/geometry_to_mesh_flythrough.py),
which draws raw emit and junction-prepared strips side by side at a junction
zoom — the two forms are hard to compare any other way.

## Tolerance audit (2026-08-30)

Sweep of every tolerance-like constant and inline numeric comparison in the
package (**excluding** `tests/` and `visualisation/`), classified by what the
number stands in for. A tolerance is only a defect when it substitutes for a
quantity that is knowable exactly.

**(a) Substituting for a known exact answer — the bug class.**

| Site | Verdict |
|---|---|
| `_SKIN_RAY_CAP_BBOX_MARGIN_M` proximity box | fixed — declared surface side (SG-001) |
| `_CAP_ENDPOINT_ON_WEB_TOL_M` deciding whether to relocate a cap end | fixed, then **deleted** — nothing relocates, so nothing decides (SG-003, SG-004) |
| web foot ← nearest-point projection | fixed — emit extent corrected (SG-002) |
| cap↔web node ← mesher `ENDPOINT_TOL_FRAC` | cap **ends** fixed (SG-004); cap **interiors** open (SG-005) |

**(b) Correctly scaled design rules — not numerical tolerances at all.**

`min_web_gap_frac = 0.02` (webs closer than 2 % of chord collapse into one) and
`min_cavity_depth_m` are structural policy, chord-relative, and belong where
they are.

**(c) Legitimate numerics — correct as they stand.**

- `inner_y_at_x`: 240 samples + 10 bisections to locate inner-skin crossings.
  A polygon-offset crossing has no closed form, so root-finding *is* the exact
  answer available. Convergence, not classification.
- `abs(twist) > 1e-10`, `area > 1e-16`, `1e-9` ring-closure checks,
  `_MIN_SEGMENT_LENGTH_M = 1e-12`, `_SKIN_RAY_T_MIN_M = 1e-9` — floating-point
  is-zero and degenerate-geometry guards.
- `_CAP_WEB_JUNCTION_MERGE_ARC_M` and `vertex_coincide_tol_m` in
  `insert_cap_web_interior_junctions` — de-duplication of inserted vertices,
  not classification of geometry.

**(d) Scale-dependent but safe — fixed anyway.**

The skin-cut merge tolerance was the only one in the junction path expressed in
absolute metres while everything around it was chord-relative. It is now
`_MERGE_S_TOL_FRAC` × arc length. The absolute `_MERGE_S_TOL_M` constant that
used to sit beside it had no consumers once the derived form landed and has been
deleted; a caller that needs an absolute value still passes `merge_s_tol_m`
explicitly to `split_skin_at_junctions`.

### The trap this class hides

Making one side of a junction exact can break the *other* side's detection.
Placing a web vertex precisely on a cap turns a polyline crossing into a
tangency, and `intersect_open_polylines_2d` then finds nothing. SG-005 records
the measured swap on `4D-F`: web gap 1570 µm → 0, cap gap 0 → 1056 µm. Junction
exactness has to be established for both participants in the same pass, from one
solved crossing, after both polylines are final.

---

## SG-001

**Box-cap (family D) midline loses its curvature during topology preparation**

**Status:** Fixed — twice; the first fix was a better guess and was superseded
**Found:** 2026-08-30
**Area:** `midlines/cap_skin_ray_resample.py`

### Symptom

The family-**D** box-cap midline loses its curvature between the raw emit and
the junction-prepared strip. The mesh built on it is wrong, not just the picture.

### Evidence

`2D-F`, 6 mm skin / 14 mm cap: the cap goes 105 → **8** points, sagitta
10.139 → **6.121 mm**, and the middle ~80 % of the cap becomes one straight
chord. Mesh nodes sit **5.968 mm** off the true cap midline — **43 % of cap
thickness**. Refining does not help; the elements subdivide the wrong chord.
Only **6 of 24** skin vertices above the cap survive the bbox pre-filter, all
clustered at the cap ends.

### Root cause

`cap_skin_ray_resample.py` rejected skin vertices outside the cap bounding box
plus a **fixed** `_SKIN_RAY_CAP_BBOX_MARGIN_M = 5 mm`, but the skin midline sits
`(skin_t + cap_t)/2` from the cap midline — 10.0 mm at these gauges. The margin
was narrower than the thing it was filtering, so the rays had almost no origins.
Margin sweep: 5 mm → 8 pts / 5.971 mm error; 10 mm → 25 pts / 0.071 mm;
12 mm → 26 pts / 0.002 mm.

### Verification

First fixed by deriving the margin per cap from its own gauge
(`required_cap_bbox_margin_m` = `1.25 × (cap_t + skin_t)/2`): `2D-F` 26 pts,
sagitta 10.139 mm exact, mesh node error **0.0012 mm**.

That was a better *guess*, so it was superseded: the bounding box is gone
entirely, and cap resampling now selects skin vertices by the strips' **declared**
suction/pressure side. `required_cap_bbox_margin_m` and
`_SKIN_RAY_BBOX_MARGIN_SAFETY` have been deleted (0 references).

Pinned by `tests/test_cap_skin_ray_resample_fidelity.py`, which asserts the
*outcome* (prepared cap tracks raw cap) rather than the mechanism, and so
survived the rework unaltered.

### Cleanup, 2026-08-30

`ShellStripTopologySpec.skin_ray_cap_bbox_margin_m` and the matching
`shell_mesh_inputs_from_section(..., skin_ray_cap_bbox_margin_m=...)` parameter
outlived the mechanism they configured. `build_shell_strip_topology` never read
the field, so a caller could set the margin and get silence — the field's own
docstring admitted this, but the handoff signature did not. Both deleted; no
caller passed either. `_SKIN_RAY_CAP_BBOX_MARGIN_M` itself is retained and
re-exported for the reason in SG-006.

---

## SG-002

**Shear-web midline kinks at the foot during junction preparation**

**Status:** Fixed at the root (emit extent)
**Found:** 2026-08-30
**Area:** `sections/components/shear_web.py` — `ShearWeb.midline_polyline`

### Symptom

The projected segment that reaches the skin is not parallel to the rest of the
web.

### Evidence

The raw web is a capsule axis, straight to **0.000 µm**. After preparation the
last segment leans **1.03–3.43°** off the web axis at zero twist and
**3.92–8.45°** at 15° twist, putting the junction node **0.14–1.19 mm** off the
web axis on an 8 mm web (~15 % of web thickness).

Controls: a symmetric NACA 0012 gives identical error at both ends of a web
(2.14° / 0.297 mm), and `2D-F` ≡ `2D-CN` at zero twist, where flapwise and
chord-normal coincide.

### Root cause

**An emit-extent error, not a topology error.** `ShearWeb.midline_polyline`
interpolated between the two **inner-mould-line anchors** — the right locus for
building the *solid*, but half a skin gauge short of where the web's
**mid-surface** ends. Measured: the anchor sits at exactly 0.000 mm from the IML
and −3.000 mm from the skin mid-surface on a 6 mm gauge.

Because the strip arrived short, `split_skin_at_junctions` had to **relocate**
the foot, and relocating requires guessing a direction. It guessed perpendicular
to the skin (`point_to_open_polyline_nearest`), which equals the web axis only at
exactly 90° — never on a cambered or twisted section.

### Verification

`ShearWeb.midline_polyline` now emits the web mid-surface out to the skin
mid-surface, solving for the step along the web axis (`half_gauge / cos θ`;
measured 3.037–3.042 mm for a 3.000 mm half gauge, θ ≈ 9.6°) rather than
assuming it.

Raw web endpoints now land on the skin mid-surface to **0.000 µm** before any
topology pass, so `split_skin_at_junctions` no longer moves them: it only
*indexes*, finding the arc length at which to split the skin. Measured across
`2D-F`/`5D-F`/`3D-CN` at 0–15° twist: topology relocation **0.00 µm**,
foot-to-skin-node **0.00 µm**, kink **0.0000°**.

Pinned by `tests/test_web_foot_axis_snap.py` — 40 cases
(`test_prepared_web_stays_straight`, 5 layouts × 2 twists × 3 airfoils, plus
`test_web_foot_lands_exactly_on_a_skin_node`, 5 layouts × 2 twists).

~~An earlier fix made topology's *guess* correct, by intersecting the web axis
with the skin instead of projecting perpendicular to it.~~ Superseded by the
above: it removed the symptom, not the need to guess.

### Cleanup, 2026-08-30

The superseded fix left its implementation behind —
`_axis_polyline_crossing_nearest` in `midlines/skin_split.py`, 45 lines,
defined and never called. Deleted. Its docstring was the clearest statement in
the package of *why* perpendicular projection is wrong, so that reasoning has
been folded into this entry rather than lost with it.

---

## SG-003

**Band-cap (B) and discrete-cap (C) ends are relocated onto the skin**

**Status:** Fixed — no relocation at all
**Found:** 2026-08-30
**Area:** `midlines/skin_split.py` — `split_skin_at_junctions`

### Symptom

Family-**B** and family-**C** cap midlines are displaced and their arc length
inflates during topology preparation. **Not** the same defect as SG-001 —
widening the bbox margin changes nothing here.

### Evidence

`2B-F` suction cap: `split_skin_at_junctions` moves the first point
`X_B 0.06373 → 0.07371` (**+9.98 mm**) and the last `0.06611 → 0.07611`
(**+10.0 mm**); arc **100.05 → 117.67 mm (+17.6 %)**. `2C-F` the same
(81.12 → 99.16 mm). `2D-F` is untouched (105 pts, arc identical).

Displacement ≈ `(skin_t + cap_t)/2` — the cap end is landing **on the skin
midline**. Ray-resample counters confirm it is not the margin: raising it
5 → 25 mm lifts `bbox_pass` 7 → 11 but `ray_hit` stays pinned at **7**, and the
endpoint move happens before the resampler runs. Residual error vs the raw cap
5.6–9.5 mm across gauges, unchanged by margin.

### Root cause

For each cap endpoint, if it was not within `_CAP_ENDPOINT_ON_WEB_TOL_M` of a
web polyline, the code snapped it onto the **nearest skin midline**. Family-D box
caps terminate on webs, so `on_web` was true and they were skipped — which is why
D never showed this. Families B and C terminate mid-bay with free ends, so both
ends got dragged ~`(skin_t + cap_t)/2` outward onto the skin, adding two diagonal
hooks. A free cap end should stay on the cap's own mid-surface; the snap is only
meaningful when the end really is at a junction.

### Verification

The answer was *no relocation at all*. Measurement settled it: a family-D cap end
is already at **0.000 mm** from the web mid-surface, and a B/C free end is
**38.6–148.6 mm** from the nearest web across 0–15° twist. The two populations
are four orders of magnitude apart, so there was never a tolerance to tune — only
a decision not to move anything.

`split_skin_at_junctions` now passes caps through untouched. Cap endpoint
displacement **10 mm → 0.0000 mm**, arc-length inflation **+17.6 % → 0.00 %**,
and B/C cap fidelity vs the raw curve **3.7–9.5 mm → 0.0000–0.0017 mm**.

B and C are now covered by `tests/test_cap_skin_ray_resample_fidelity.py`, which
also pins the invariant directly (`test_topology_never_relocates_a_cap_endpoint`).

Note that the SG-002 fix did **not** transfer: a cap end runs **0.00–0.95° from
parallel** to the skin, so "extend along its own axis to meet the skin" is
undefined for a cap — same call site, opposite correct answer.

---

## SG-004

**Cap–web junction has no shared node at a cap end**

**Status:** Fixed at emit
**Found:** 2026-08-30
**Area:** `midlines/shell_midline_export.py`

### Symptom

The cap end sat on the web mid-surface but between two web vertices. Latent, not
a live defect — output was correct.

### Evidence

Cap end to web **mid-surface** 0.000 mm, but to the nearest web **node**
0.624 mm (`2D-F`), 0.958 mm (`5D-CN`), **1.880 mm** (`3D-F`). The junction held
together only because `section_mesh` clusters endpoints within
`ENDPOINT_TOL_FRAC = 0.006` — **6 mm on a 1 m chord** — leaving `3D-F`
conforming on **4.1 mm of margin**, in a tolerance that scales with *chord*, not
with mesh density. Refining the web, shrinking the chord or raising the web count
erodes it silently, with no error raised.

### Root cause

The web is sampled independently of the caps, so nothing put a vertex where a cap
lands on it. `insert_cap_web_interior_junctions` patched this after the fact,
using `point_to_open_polyline_nearest` a fourth time.

### Verification

`midlines/shell_midline_export.py` (`_insert_web_cap_junction_nodes`) now inserts
a vertex into each web where a cap mid-surface meets it, at emit, where both are
in hand. Exact: a web midline is straight and the cap end already lies on it, so
the inserted vertex changes no geometry. Cap-end-to-web-node
**0.62–1.88 mm → 0.000 µm** across `2D-F`/`2D-CN`/`3D-F`/`4D-F`/`5D-CN`. The
on-axis membership test is a tolerance but not a fragile one — it separates
0.000 mm from 38.6–148.6 mm.

Only the **web** gets nodes at emit. Inserting into the cap there would be undone
by `resample_cap_interiors_from_skin_rays`, which rebuilds the cap interior
afterwards.

### Cleanup, 2026-08-30

Fixing the web side at emit made the cap side of the same junction unreachable.
`insert_cap_web_interior_junctions` carried a cap-endpoint-on-web branch that
inserted the nearest web-midline point for any cap end within
`_CAP_ENDPOINT_ON_WEB_TOL_M` of a web. Both of its guards now always reject:

- a family-D cap end is coincident with a web node to 0.000 µm, so the
  `vertex_coincide_tol_m = 1e-6` guard skips it;
- a family-B/C free end is 38.6–148.6 mm from the nearest web, so the
  `> _CAP_ENDPOINT_ON_WEB_TOL_M` guard skips it.

Confirmed by disabling the branch and diffing strip arrays across **108
configurations** (12 layouts × 3 twists {0°, 15°, 34.11°} × 3 chords
{1.0, 1.656, 0.241 m}): **byte-identical output, 0 strips differing**. The
branch and `_CAP_ENDPOINT_ON_WEB_TOL_M` are deleted, and
`cap_web_junctions.py` no longer imports `point_to_open_polyline_nearest`.

This is worth knowing before attacking SG-005: the earlier revision of this log
identified the deleted branch as SG-005's code, which it never was. SG-005 lives
in the **interior segment-intersection** path at the top of the same function.

**Follow-up worth checking:** three `section_shell_fea` cap-tie tests moved from
xfail to xpass (`test_untied_cap_s_and_q_diverge`,
`test_untied_cap_fi_diverges_so_the_test_discriminates`,
`test_connected_components_converge_regardless_of_cap_ties`), all tagged
[BL-014](../../../../../docs/bug_log.md#bl-014) in the repo-root log. They are
`strict=False` and documented as execution-context dependent, so this is a signal
to investigate BL-014, not a claim it is resolved.

---

## SG-005

**Interior cap–web T-junctions have a node on the cap side only**

**Status:** Open — latent, not a live defect
**Found:** 2026-08-30
**Area:** `topology/cap_web_junctions.py` — `insert_cap_web_interior_junctions`

### Symptom

Where a web crosses a cap's **middle** rather than its end, only the cap carries
a node at the crossing.

### Evidence

Exact web-axis × cap-polyline crossings, measured after the full topology pass
(re-measured 2026-08-30, post-cleanup — unchanged):

| Layout | Interior crossings | Cap-node gap | **Web-node gap** |
|---|---|---|---|
| `3D-F` | 2 | 0.0 µm | **481.8 µm** |
| `2C-F` | 2 | 0.0 µm | **624.0 µm** |
| `4D-F` | 4 | 0.0 µm | **1569.6 µm** |
| `5D-CN` | 6 | 0.0 µm | **1949.4 µm** |

Conforming only through `section_mesh`'s `ENDPOINT_TOL_FRAC` (6 mm at 1 m
chord) — **4.05 mm of margin at worst**, in a chord-scaled tolerance. Affects
layouts where a web crosses a cap interior: family D with 3 or more webs, and
family C.

### Root cause

Webs and caps are sampled independently. `insert_cap_web_interior_junctions`
closes the cap side by intersecting the two polylines — verified: it inserts
exactly one cap vertex per interior crossing (`3D-F` +1 per cap, `4D-F` +2,
`5D-CN` +3, `2C-F` +1 per cap, `2B-F` +0, which has no interior crossings). But
nothing puts the matching node on the web.

### Why the obvious fix fails

An attempt to insert the web node at emit — alongside the cap-*end* junctions,
which `_insert_web_cap_junction_nodes` does fix — **made it worse and was
reverted**. Placing a web vertex exactly on the cap makes the two polylines
*touch* rather than cross, so `intersect_open_polylines_2d` stops finding the
junction and the cap side regresses. Measured on `4D-F`: web gap 1570 µm → 0,
cap gap 0 → 1056 µm — a clean swap of which side is broken.

The same mechanism is visible in the current output: re-running
`intersect_open_polylines_2d` on prepared strips finds **nothing**, because the
cap vertex the pass just inserted has already turned every crossing into a
tangency. That is expected, and is not evidence the pass did nothing.

### Proposed fix

Run **after** the cap resample, where the cap polyline is final, and insert into
both strips from one solved crossing — i.e. `insert_cap_web_interior_junctions`
should return modified webs as well as caps. Emit cannot do it, because the cap
it would compute against is not the cap that survives resampling.

---

## SG-006

**`centerline_mesh` still draws the bounding-box filter SG-001 deleted**

**Status:** Open — figure only; no effect on geometry, strips or mesh
**Found:** 2026-08-30
**Area:** `mesh_utilities/section_mesh/visualisation/centerline_mesh.py`

### Symptom

`_add_skin_inward_rays_class_c_near_caps` is documented as drawing "Class C ray
directions used by cap interior resampling", but it selects which skin vertices
get an arrow by reimplementing the cap bounding box plus
`_SKIN_RAY_CAP_BBOX_MARGIN_M` — the exact 5 mm proximity box that SG-001 proved
was the defect and removed from the resampler.

### Consequence

The figure shows the *old* algorithm. On the SG-001 reference case it would draw
arrows from roughly 6 of 24 skin vertices, clustered at the cap ends, where the
real resampler now uses every vertex on the declared side. Anyone reading the
plot to understand cap resampling is being shown the bug, not the fix.

Geometry, strips and mesh are unaffected — this code path only emits arrows.

### Why it is still here

It is the sole remaining consumer of `_SKIN_RAY_CAP_BBOX_MARGIN_M` and the reason
that constant, and its re-export from `topology/shell_strip_topology.py`, are
retained. Closing this entry makes both deletable.

### Fix

Replace the bbox test with the same declared-side selection the resampler uses
(`skin_side` / `surface` on the strip, as in
`concat_skin_ring_vertices(..., with_sides=True)`), then delete the constant and
its re-export. Left open rather than done blind: the demo is covered by
`section_mesh/tests/test_centerline_mesh_plots.py`, and what the figure is
*meant* to teach should be settled before its content changes.
