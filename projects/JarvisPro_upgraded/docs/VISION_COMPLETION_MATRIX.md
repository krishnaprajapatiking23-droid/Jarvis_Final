# Vision Completion Matrix

Roadmap section 30. Generated from the state of the repository after this
build, not from intent.

**Environment these results were measured in:** Linux, headless (no `DISPLAY`),
no camera device, no reachable model runtime. Tesseract 5.3.4, OpenCV, Pillow
and NumPy are present. `mss`, `pyautogui` and `torch` are not installed and
could not be installed (no network).

Status meanings:

| Status | Meaning |
|---|---|
| ✅ COMPLETE | implemented, integrated, and verified by a test that measures the behaviour |
| 🟨 PARTIAL | real functionality exists, significant capability remains |
| 🔌 EXTERNAL | implemented, blocked only by an unavailable service, model or credential |
| 🧪 UNVERIFIED | implemented, cannot be live-tested in this environment |
| ⬜ NOT IMPLEMENTED | not built |

---

## Matrix

| # | Feature | Status | Implementation | Test | Evidence | Remaining |
|---|---|---|---|---|---|---|
| 1 | Full Screen Understanding | 🟨 PARTIAL | `vision/analyzer.py` `ScreenAnalyzer.analyze` | `ScreenUnderstandingTests` (13) | Returns structured `{screen, elements, text, buttons, inputs, counts}` with coordinates and confidence; 14 elements from the login screen | No accessibility-API or DOM source; no vision model, so unlabelled graphics and semantic layout are uninterpreted |
| 2 | Screenshot Analysis | 🟨 PARTIAL | `ScreenAnalyzer.analyze` (capture → OCR → detect → per-region OCR → classify) | `ScreenUnderstandingTests` | Answers "what buttons exist", "where is the search box", "what text is displayed" | Cannot answer "what application is visible" without a window manager |
| 3 | OCR | ✅ COMPLETE | `vision/perception.py` `OCRProvider` | `OCRTests` (8) | Word boxes + confidence via `image_to_data`; adaptive inversion recovers light-on-dark labels; corrupt/blank/missing input all handled | — |
| 4 | Image Understanding | 🔌 EXTERNAL | `VisionModelProvider` | `ProviderHealthTests` | Provider implemented against `core.model_router`; correctly reports `not configured` | Needs a reachable vision model (`gemma3:12b` configured, never reached) |
| 5 | Camera Input | 🧪 UNVERIFIED | `providers.py` `CameraProvider` | `MockCameraTests` (7) | Discovery, open/close, frame, continuous, resolution/FPS, disconnect recovery; full pipeline tested via `MockCamera` | No `/dev/video*` here — never run against real hardware |
| 6 | Object Detection | ⬜ NOT IMPLEMENTED | — | — | — | No provider written; `torch` unavailable and uninstallable offline |
| 7 | UI Understanding | 🟨 PARTIAL | `perception.py` `ElementDetector` + `classify` | `ElementDetectionTests`, `ScreenUnderstandingTests` | Buttons, inputs, checkboxes, dropdowns, labels, text, icons from pixels alone | Radio, tab, slider, toolbar, scrollarea, menu, dialog not distinguished; no accessibility API |
| 8 | Button / Text Understanding | ✅ COMPLETE | `classify` + `ACTION_WORDS` / `DESTRUCTIVE_WORDS` | `test_destructive_action_is_flagged` and 3 others | "Delete" → button, destructive=True; "Keep" → button, destructive=False; colour recorded | — |
| 9 | Element Identification | ✅ COMPLETE | `types.py` `Element.stable_id` | `ElementIdentityTests` (6) | Content-derived ids stable across 2px jitter, differ on real move or text change | — |
| 10 | Coordinate Detection | ✅ COMPLETE | `types.py` `CoordinateSpace`, `MonitorLayout` | `CoordinateTests` (11) | DPI scaling (1.0/1.25/2.0), window-relative, multi-monitor with negative origin, roundtrip stable | Not exercised against a real multi-monitor desktop |
| 11 | Visual Grounding | ✅ COMPLETE | `analyzer.py` `VisualGrounding` | `GroundingTests` (9) | Resolves by text, colour, kind, spatial relation; refuses when top two are within 0.12; `test_no_hardcoded_coordinates_anywhere` proves positions come from pixels | — |
| 12 | Visual Computer Control | ⬜ NOT IMPLEMENTED | — | — | — | No click/type/scroll layer; would need `pyautogui` and a display |
| 13 | Document Understanding | 🟨 PARTIAL | `OCRProvider` + `testkit.Document` | `DocumentOCRTests` (4) | Invoice total `2082.60` read with a box within 25px of its rendered position | No PDF page rendering, layout detection, table extraction or question answering |
| 14 | Screen State | ✅ COMPLETE | `analyzer.py` `ScreenState` | `StateComparisonTests` (7) | Holds current + previous observation and image, with timestamps and confidence | — |
| 15 | UI State Comparison | ✅ COMPLETE | `ScreenState.diff` | `StateComparisonTests` | Added / removed / moved / text-changed / state-changed; a moved button reports as moved, not add+remove | — |
| 16 | Visual Action Verification | ⬜ NOT IMPLEMENTED | — | — | — | The comparison primitive it needs exists; the before→act→after→verify loop does not |
| 17 | Vision Memory | ⬜ NOT IMPLEMENTED | — | — | — | Not built |
| 18 | Screen-Change Detection | ✅ COMPLETE | `pixel_difference`, `changed`, `changed_regions` | `ChangeDetectionTests` (6) | Identical frames → 0.0; region localisation finds an added button; 3.1 ms per comparison | Perceptual (hash-based) difference not implemented |

---

## Not built in this pass

Object detection, visual computer control, visual action verification, vision
memory, AGI/browser/voice integration, and the security and privacy layers for
visual operations. These are listed as ⬜ rather than given a partial status,
because no code for them exists.

---

## Bugs found and fixed

| Bug | Root cause | Fix | Test | Result |
|---|---|---|---|---|
| Whole-screen OCR read "Login" as "gin" | White label on a blue fill; a single grayscale pass loses it | `read_adaptive` reads normal + inverted, keeps the higher-scoring pass; analyzer re-reads every filled region | `test_light_on_dark_button_label_is_read_correctly` | Fixed |
| One button reported twice | Detector finds the button *and* its inner text box; IoU is only 0.16 so NMS misses it | Suppress boxes contained within a control at <85% of its area | `test_buttons_are_found_exactly_once_each` | Fixed |
| Every text label classified as a button | "filled" judged purely by distance from background; a text region's mean colour is also far from it | Require colour distance **and** low pixel variance (buttons std≈24–32, text std≈65–82) | `test_filled_control_is_uniform_and_text_is_not` | Fixed |
| Green Submit button classified as an input | Its white label was recovered into `label` by region OCR, but `classify` tested `inner_text`, which was empty | `classify` tests `has_text` = inner_text **or** label | `test_a_filled_green_button_is_a_button_not_an_input` | Fixed |
| Checkboxes never detected | 24px checkbox is 576px², below the 900px² floor | Floor lowered to 320; extent and side filters carry noise rejection | `test_detection_finds_a_checkbox` | Fixed |
| All grounding refused as ambiguous | Duplicate detections of one widget scored identically | Dedupe co-located same-text candidates before the ambiguity check | `GroundingTests` | Fixed |
| "the Username field" could not be grounded | An input carries no text of its own; only `element.text` was searched | Grounding also searches `attributes["label"]` | `test_grounding_resolves_an_input_by_its_label` | Fixed |
| Unlabelled button classified as an input | "Go" was too short for OCR; no text → fell to the input branch | A filled uniform control with no readable text is a button; inputs are unfilled | `test_a_moved_element_is_a_move_not_an_add_and_a_remove` | Fixed |
| A moved element reported as add+remove | `_match_by_text` returned None for empty text | Geometric fallback: same kind and ≥0.9 size ratio | `test_a_moved_element_is_a_move_not_an_add_and_a_remove` | Fixed |
| Duplicate element ids in one observation | Two detections resolved to the same stable id | Keep the higher-confidence one | — | Fixed |
| Vision model claimed **available** with no runtime | `router.health()` reports configured models as `available: True` with `runs: 0` | Require a model declaring the `vision` capability **and** ≥1 successful run | `test_vision_model_does_not_claim_an_unreachable_model` | Fixed |
| `describe_image` would have raised TypeError | Called `router.ask(prompt, image=…, model=…)`; the real signature is `(prompt, capability, options)` | Corrected the call | — | Fixed (latent) |

---

## Measured performance

Real measurements on the 900×620 login screen, n=5. Not estimates.

| Operation | Mean | Range |
|---|---|---|
| OCR, full screen | 217.8 ms | 197–253 |
| Element detection | 9.5 ms | 9–11 |
| Full screen analysis | 2170.9 ms | 1999–2385 |
| Visual grounding | 0.1 ms | 0–1 |
| Pixel change detection | 3.1 ms | 3–5 |
| Document OCR (860×1100) | 474.6 ms | 467–479 |

Full analysis is dominated by per-region OCR — each filled control costs an
extra tesseract pass. The change-detection primitive at 3 ms is what makes
skipping unchanged frames worthwhile.

---

## Health report

| Capability | State | Detail |
|---|---|---|
| SCREEN_CAPTURE | unavailable | no display server (headless host) |
| OCR | available | tesseract 5.3.4 |
| UI_DETECTION | available | OpenCV |
| CAMERA | unavailable | no camera device found (`/dev/video*`) |
| IMAGE_UNDERSTANDING | not configured | `gemma3:12b` configured but never reached |

---

## Test results

- Vision tests: **94 passed, 0 failed, 0 skipped**
- Full project suite: **747 passed, 1 failed, 2 skipped**

The single failure is `test_subsystems_batch3.py`, which passes standalone
(63 checks, 0 failed) and fails only in-suite — cross-test state pollution,
traced to `jarvis_core/automation_manager.py` returning `reason=None` for a
headless window move after another test has run. It predates this work.
