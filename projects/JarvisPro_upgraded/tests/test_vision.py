"""Vision tests.

Scored against the ground truth of what the test kit actually drew, so
"the detector found the Submit button" is a measured claim rather than an
inspection. The images are real pixels and tesseract genuinely reads them, so
these exercise the real OCR and computer-vision path.

What is NOT covered here, and is marked unverified rather than skipped
silently: live screen capture (no display), live camera (no device) and a
vision-language model (none reachable). The provider health tests below assert
that those report themselves honestly instead of claiming to work.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from vision.analyzer import (
    ScreenAnalyzer,
    ScreenState,
    VisualGrounding,
    changed,
    changed_regions,
    pixel_difference,
)
from vision.perception import ElementDetector, OCRProvider, classify, colour_name
from vision.providers import (
    AVAILABLE,
    NOT_AVAILABLE,
    NOT_CONFIGURED,
    NO_DEVICE,
    CameraProvider,
    MockCamera,
    ScreenshotProvider,
    StaticImageProvider,
    VisionModelProvider,
    VisionResult,
    probe_all,
)
from vision.testkit import (
    Document,
    UIScreen,
    available,
    dialog_screen,
    form_screen,
    invoice,
    login_screen,
    state_pair,
)
from vision.types import (
    BBox,
    CoordinateSpace,
    Element,
    MonitorLayout,
    merge_boxes,
    suppress_overlaps,
)

PILLOW = available()


def needs_pillow(test):
    return unittest.skipUnless(PILLOW, "Pillow unavailable")(test)


class GeometryTests(unittest.TestCase):

    def test_negative_size_is_rejected(self):
        with self.assertRaises(ValueError):
            BBox(0, 0, -5, 10)

    def test_center_and_edges(self):
        box = BBox(100, 200, 80, 40)

        self.assertEqual(box.center, (140, 220))
        self.assertEqual((box.right, box.bottom), (180, 240))

    def test_containment_and_intersection(self):
        outer = BBox(0, 0, 100, 100)
        inner = BBox(10, 10, 20, 20)
        apart = BBox(500, 500, 10, 10)

        self.assertTrue(outer.contains_box(inner))
        self.assertFalse(inner.contains_box(outer))
        self.assertTrue(outer.intersects(inner))
        self.assertFalse(outer.intersects(apart))
        self.assertIsNone(outer.intersection(apart))

    def test_iou(self):
        box = BBox(0, 0, 10, 10)

        self.assertEqual(box.iou(box), 1.0)
        self.assertEqual(box.iou(BBox(100, 100, 10, 10)), 0.0)

    def test_nested_box_has_low_iou(self):
        """The reason NMS alone could not remove a button's inner text box."""

        outer = BBox(240, 402, 147, 43)
        inner = BBox(285, 415, 59, 17)

        self.assertTrue(outer.contains_box(inner))
        self.assertLess(outer.iou(inner), 0.25)

    def test_merge_boxes(self):
        merged = merge_boxes([BBox(0, 0, 10, 10), BBox(20, 20, 10, 10)])

        self.assertEqual((merged.x, merged.y, merged.right, merged.bottom), (0, 0, 30, 30))

    def test_merge_of_nothing_is_none(self):
        self.assertIsNone(merge_boxes([]))

    def test_suppression_keeps_the_strongest(self):
        kept = suppress_overlaps(
            [(BBox(0, 0, 50, 50), 0.9), (BBox(2, 2, 50, 50), 0.4)]
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0][1], 0.9)

    def test_suppression_keeps_separate_boxes(self):
        kept = suppress_overlaps(
            [(BBox(0, 0, 50, 50), 0.9), (BBox(500, 500, 50, 50), 0.8)]
        )

        self.assertEqual(len(kept), 2)


class CoordinateTests(unittest.TestCase):

    def test_unscaled_is_identity(self):
        space = CoordinateSpace(1920, 1080)

        self.assertEqual(space.to_screen(100, 200), (100, 200))

    def test_scaling_is_applied(self):
        """A 200% display: a screenshot pixel is half a logical pixel."""

        space = CoordinateSpace(2880, 1800, scale=2.0)

        self.assertEqual(space.to_screen(800, 600), (400, 300))

    def test_fractional_scaling(self):
        space = CoordinateSpace(2400, 1350, scale=1.25)

        self.assertEqual(space.to_screen(1000, 500), (800, 400))

    def test_roundtrip_is_stable(self):
        space = CoordinateSpace(2880, 1800, scale=1.5)

        self.assertEqual(space.to_image(*space.to_screen(600, 450)), (600, 450))

    def test_zero_scale_is_rejected(self):
        with self.assertRaises(ValueError):
            CoordinateSpace(100, 100, scale=0)

    def test_invalid_size_is_rejected(self):
        with self.assertRaises(ValueError):
            CoordinateSpace(0, 100)

    def test_monitor_origin_offsets_the_result(self):
        space = CoordinateSpace(1920, 1080, origin=(1920, 0), monitor="second")

        self.assertEqual(space.to_screen(10, 10), (1930, 10))

    def test_window_relative_conversion(self):
        space = CoordinateSpace(1920, 1080)
        window = BBox(300, 150, 800, 600)

        self.assertEqual(space.to_window(400, 250, window), (100, 100))
        self.assertEqual(space.from_window(100, 100, window), (400, 250))

    def test_click_point_accounts_for_scaling(self):
        space = CoordinateSpace(2880, 1800, scale=2.0)
        element = Element("button", BBox(800, 600, 200, 80), "Submit")

        self.assertEqual(space.click_point(element), (450, 320))

    def test_layout_handles_a_negative_origin(self):
        """A monitor to the left of the primary has a negative origin."""

        layout = MonitorLayout(
            [
                CoordinateSpace(1920, 1080, 1.0, (0, 0), "primary"),
                CoordinateSpace(2560, 1440, 1.25, (-2048, 0), "left"),
            ]
        )
        bounds = layout.virtual_bounds()

        self.assertEqual(bounds.x, -2048)
        self.assertEqual(layout.for_point(-500, 100).monitor, "left")
        self.assertEqual(layout.for_point(100, 100).monitor, "primary")

    def test_point_outside_every_monitor(self):
        layout = MonitorLayout([CoordinateSpace(1920, 1080)])

        self.assertIsNone(layout.for_point(9000, 9000))

    def test_clamp_keeps_a_point_on_screen(self):
        space = CoordinateSpace(1920, 1080)

        self.assertEqual(space.clamp(5000, -20), (1919, 0))


class ElementIdentityTests(unittest.TestCase):

    def test_id_is_stable_across_small_jitter(self):
        first = Element("button", BBox(740, 540, 120, 42), "Submit")
        second = Element("button", BBox(742, 541, 120, 42), "Submit")

        self.assertEqual(first.id, second.id)

    def test_id_differs_for_different_text(self):
        first = Element("button", BBox(740, 540, 120, 42), "Submit")
        second = Element("button", BBox(740, 540, 120, 42), "Cancel")

        self.assertNotEqual(first.id, second.id)

    def test_id_differs_for_a_real_move(self):
        first = Element("button", BBox(740, 540, 120, 42), "Submit")
        second = Element("button", BBox(200, 100, 120, 42), "Submit")

        self.assertNotEqual(first.id, second.id)

    def test_interactivity_is_derived_from_kind(self):
        self.assertTrue(Element("button", BBox(0, 0, 10, 10)).interactive)
        self.assertFalse(Element("label", BBox(0, 0, 10, 10)).interactive)

    def test_unknown_kind_is_normalised(self):
        self.assertEqual(Element("wormhole", BBox(0, 0, 10, 10)).kind, "unknown")

    def test_round_trip(self):
        original = Element("button", BBox(1, 2, 3, 4), "Go", 0.8)
        restored = Element.from_dict(original.report())

        self.assertEqual(restored.kind, original.kind)
        self.assertEqual(restored.text, original.text)
        self.assertEqual(restored.bbox, original.bbox)


class ProviderHealthTests(unittest.TestCase):
    """Providers must report honestly rather than claim to work."""

    def test_result_failure_carries_a_machine_readable_type(self):
        result = VisionResult.fail("VISION_TIMEOUT", "too slow")

        self.assertFalse(result)
        self.assertEqual(result.report()["error_type"], "VISION_TIMEOUT")

    def test_headless_screenshot_reports_no_display(self):
        provider = ScreenshotProvider()

        if provider.available:
            self.skipTest("this host has a display")

        self.assertFalse(provider.capture().success)
        self.assertIn(provider.health()["state"], (NOT_AVAILABLE, NOT_CONFIGURED))

    def test_camera_without_a_device_does_not_raise(self):
        provider = CameraProvider()
        result = provider.frame()

        if provider.available:
            self.skipTest("this host has a camera")

        self.assertFalse(result.success)
        self.assertTrue(result.recoverable)

    def test_vision_model_does_not_claim_an_unreachable_model(self):
        """Configured is not reachable - the distinction section 62 requires."""

        provider = VisionModelProvider()

        if provider.available:
            self.skipTest("a vision model is genuinely reachable here")

        report = provider.health()

        self.assertIn(report["state"], (NOT_AVAILABLE, NOT_CONFIGURED))
        self.assertFalse(provider.describe_image(None).success)

    def test_probe_all_separates_available_from_unavailable(self):
        report = probe_all([ScreenshotProvider(), CameraProvider(), OCRProvider()])

        self.assertIn("available", report)
        self.assertIn("unavailable", report)

    def test_timeout_is_reported_not_hung(self):
        import time

        class Slow(OCRProvider):
            def _probe(self):
                return True, "", {}

        result = Slow().guard(lambda: time.sleep(2), timeout=0.15)

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "VISION_TIMEOUT")

    def test_exception_becomes_a_structured_failure(self):
        class Boom(OCRProvider):
            def _probe(self):
                return True, "", {}

        def explode():
            raise RuntimeError("detector crashed")

        result = Boom().guard(explode)

        self.assertFalse(result.success)
        self.assertIn("RuntimeError", result.message)


@needs_pillow
class MockCameraTests(unittest.TestCase):
    """The camera pipeline, exercised without hardware (section 46)."""

    def setUp(self):
        self.frame = login_screen().render()

    def test_mock_declares_itself_simulated(self):
        camera = MockCamera([self.frame])

        self.assertTrue(camera.health()["simulated"])
        self.assertIn("not live camera", camera.health()["note"])

    def test_frames_flow_and_are_marked_degraded(self):
        camera = MockCamera([self.frame])
        result = camera.frame()

        self.assertTrue(result.success)
        self.assertTrue(result.degraded)

    def test_camera_with_no_frames_is_unavailable(self):
        result = MockCamera([]).frame()

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, NO_DEVICE)

    def test_busy_camera_is_reported_as_recoverable(self):
        camera = MockCamera([self.frame])
        camera.set_busy(True)
        result = camera.open()

        self.assertFalse(result.success)
        self.assertTrue(result.recoverable)
        self.assertIn("in use", result.message)

    def test_disconnect_mid_stream_closes_the_handle(self):
        camera = MockCamera([self.frame], fail_after=1)

        self.assertTrue(camera.frame().success)
        self.assertFalse(camera.frame().success)
        self.assertFalse(camera.opened)

    def test_close_is_safe_when_never_opened(self):
        MockCamera([self.frame]).close()

    def test_camera_frame_feeds_the_analyzer(self):
        camera = MockCamera([self.frame])
        captured = camera.frame()
        observation = ScreenAnalyzer().analyze(captured.data)

        self.assertTrue(observation.success)
        self.assertTrue(observation.data.elements)


@needs_pillow
class OCRTests(unittest.TestCase):

    def setUp(self):
        self.ocr = OCRProvider()

        if not self.ocr.available:
            self.skipTest(f"tesseract unavailable: {self.ocr.health()['reason']}")

        self.image = login_screen().render()

    def test_words_carry_boxes_and_confidence(self):
        result = self.ocr.read(self.image)

        self.assertTrue(result.success)
        self.assertTrue(result.data)

        for span in result.data:
            self.assertGreater(span.bbox.area, 0)
            self.assertGreater(span.confidence, 0.0)

    def test_known_text_is_read(self):
        result = self.ocr.read_text(self.image)

        self.assertIn("Username", result.data)
        self.assertIn("Password", result.data)

    def test_phrases_are_joined_from_words(self):
        spans = self.ocr.read(self.image).data
        phrases = [p.text for p in self.ocr.phrases(spans)]

        self.assertIn("Sign in to continue", phrases)

    def test_region_read_is_confined_to_the_region(self):
        region = BBox(0, 0, 400, 120)
        result = self.ocr.read(self.image, region=region)

        for span in result.data:
            self.assertLess(span.bbox.y, 140)

    def test_adaptive_read_recovers_a_light_on_dark_label(self):
        """A white label on a blue button: the whole-page pass reads it wrongly."""

        button = login_screen().find("Login")
        result = self.ocr.read_adaptive(self.image, region=button.bbox)

        self.assertTrue(result.success)
        self.assertIn("login", " ".join(s.text for s in result.data).lower())

    def test_missing_image_is_reported_not_raised(self):
        result = self.ocr.read(None)

        self.assertFalse(result.success)
        self.assertFalse(result.recoverable)

    def test_corrupt_image_is_reported_not_raised(self):
        path = os.path.join(tempfile.mkdtemp(), "broken.png")

        with open(path, "wb") as handle:
            handle.write(b"this is not a png")

        result = self.ocr.read(path)

        self.assertFalse(result.success)

    def test_blank_image_yields_no_text_without_failing(self):
        from PIL import Image

        result = self.ocr.read(Image.new("RGB", (200, 120), (255, 255, 255)))

        self.assertTrue(result.success)
        self.assertEqual(result.data, [])


@needs_pillow
class ElementDetectionTests(unittest.TestCase):

    def setUp(self):
        self.detector = ElementDetector()

        if not self.detector.available:
            self.skipTest("OpenCV unavailable")

    def test_colour_naming(self):
        self.assertEqual(colour_name((58, 120, 220)), "blue")
        self.assertEqual(colour_name((200, 60, 60)), "red")
        self.assertEqual(colour_name((32, 160, 90)), "green")
        self.assertEqual(colour_name((250, 250, 250)), "white")

    def test_filled_control_is_uniform_and_text_is_not(self):
        """The measurement that separates a button from a line of prose."""

        image = login_screen().render()
        _, button_spread = self.detector.region_fill(image, BBox(60, 400, 150, 46))
        _, text_spread = self.detector.region_fill(image, BBox(59, 135, 90, 22))

        self.assertLess(button_spread, 45.0)
        self.assertGreater(text_spread, 45.0)

    def test_detection_finds_the_drawn_buttons(self):
        screen = login_screen()
        boxes = [b for b, _ in self.detector.detect(screen.render()).data]

        for label in ("Login", "Cancel"):
            widget = screen.find(label)
            self.assertTrue(
                any(b.iou(widget.bbox) > 0.7 for b in boxes),
                f"{label} button not detected",
            )

    def test_detection_finds_a_checkbox(self):
        """A 24px checkbox is 576 square pixels - it must not be filtered out."""

        screen = login_screen()
        boxes = [b for b, _ in self.detector.detect(screen.render()).data]
        checkbox = [w for w in screen.widgets if w.kind == "checkbox"][0]

        self.assertTrue(any(b.iou(checkbox.bbox) > 0.5 for b in boxes))

    def test_blank_screen_yields_no_widgets(self):
        from PIL import Image

        result = self.detector.detect(Image.new("RGB", (600, 400), (245, 245, 247)))

        self.assertTrue(result.success)
        self.assertEqual(result.data, [])

    def test_missing_image_is_reported(self):
        self.assertFalse(self.detector.detect(None).success)


@needs_pillow
class ScreenUnderstandingTests(unittest.TestCase):

    def setUp(self):
        self.analyzer = ScreenAnalyzer()

        if not self.analyzer.ocr.available:
            self.skipTest("tesseract unavailable")

    def observe(self, screen):
        result = self.analyzer.analyze(screen.render())
        self.assertTrue(result.success)

        return result.data

    def test_structure_is_returned_not_just_text(self):
        observation = self.observe(login_screen())
        report = observation.report()

        self.assertEqual(report["screen"]["width"], 900)
        self.assertIn("elements", report)
        self.assertIn("counts", report)

    def test_buttons_are_found_exactly_once_each(self):
        """One widget must not be reported twice from its own inner text box."""

        observation = self.observe(login_screen())
        labels = sorted(b.text for b in observation.buttons)

        self.assertEqual(labels, ["Cancel", "Login"])

    def test_button_centre_matches_ground_truth(self):
        screen = login_screen()
        observation = self.observe(screen)
        truth = screen.find("Login").bbox.center
        found = [b for b in observation.buttons if b.text == "Login"][0]

        self.assertLess(abs(found.center[0] - truth[0]), 8)
        self.assertLess(abs(found.center[1] - truth[1]), 8)

    def test_light_on_dark_button_label_is_read_correctly(self):
        observation = self.observe(login_screen())

        self.assertIn("Login", [b.text for b in observation.buttons])

    def test_inputs_are_matched_to_their_labels(self):
        observation = self.observe(login_screen())
        labels = sorted(
            str(i.attributes.get("label", "")) for i in observation.inputs
        )

        self.assertEqual(labels, ["Password", "Username"])

    def test_a_filled_green_button_is_a_button_not_an_input(self):
        observation = self.observe(form_screen())

        self.assertIn("Submit", [b.text for b in observation.buttons])

    def test_destructive_action_is_flagged(self):
        observation = self.observe(dialog_screen())
        delete = [b for b in observation.buttons if b.text == "Delete"]

        self.assertTrue(delete)
        self.assertTrue(delete[0].attributes.get("destructive"))

    def test_non_destructive_button_is_not_flagged(self):
        observation = self.observe(dialog_screen())
        keep = [b for b in observation.buttons if b.text == "Keep"]

        self.assertTrue(keep)
        self.assertFalse(keep[0].attributes.get("destructive"))

    def test_button_colour_is_recorded(self):
        observation = self.observe(login_screen())
        colours = {b.text: b.attributes.get("colour") for b in observation.buttons}

        self.assertEqual(colours.get("Login"), "blue")
        self.assertEqual(colours.get("Cancel"), "red")

    def test_observation_admits_it_is_degraded_without_a_vision_model(self):
        """Section 62: OCR plus CV must not be called visual understanding."""

        observation = self.observe(login_screen())

        if self.analyzer.vision_model is None:
            self.assertTrue(observation.degraded)
            self.assertTrue(
                any("not full visual understanding" in l for l in observation.limitations)
            )

    def test_invalid_input_is_reported_not_raised(self):
        self.assertFalse(self.analyzer.analyze(None).success)

    def test_corrupt_image_is_reported_not_raised(self):
        path = os.path.join(tempfile.mkdtemp(), "bad.png")

        with open(path, "wb") as handle:
            handle.write(b"nonsense")

        self.assertFalse(self.analyzer.analyze(path).success)

    def test_static_provider_feeds_the_pipeline(self):
        provider = StaticImageProvider([login_screen().render()])
        captured = provider.capture()

        self.assertTrue(captured.success)
        self.assertTrue(captured.degraded)
        self.assertTrue(self.analyzer.analyze(captured.data).success)


@needs_pillow
class GroundingTests(unittest.TestCase):

    def setUp(self):
        self.analyzer = ScreenAnalyzer()

        if not self.analyzer.ocr.available:
            self.skipTest("tesseract unavailable")

        self.grounding = VisualGrounding()
        self.screen = login_screen()
        self.observation = self.analyzer.analyze(self.screen.render()).data

    def test_parse_extracts_constraints(self):
        parsed = self.grounding.parse("click the blue Submit button")

        self.assertEqual(parsed["kind"], "button")
        self.assertEqual(parsed["colour"], "blue")
        self.assertIn("submit", parsed["label"])

    def test_parse_extracts_a_spatial_relation(self):
        parsed = self.grounding.parse("click the box next to Notifications")

        self.assertEqual(parsed["relation"], "near")
        self.assertIn("notifications", parsed["anchor"])

    def test_grounding_resolves_a_named_button_to_the_right_place(self):
        result = self.grounding.ground("click the Login button", self.observation)

        self.assertTrue(result["found"], result.get("reason"))
        truth = self.screen.find("Login").bbox.center
        found = result["element"].center

        self.assertLess(abs(found[0] - truth[0]), 10)
        self.assertLess(abs(found[1] - truth[1]), 10)

    def test_grounding_by_colour_alone(self):
        result = self.grounding.ground("click the red button", self.observation)

        self.assertTrue(result["found"])
        self.assertEqual(result["element"].text, "Cancel")

    def test_grounding_resolves_an_input_by_its_label(self):
        result = self.grounding.ground("the Username field", self.observation)

        self.assertTrue(result["found"], result.get("reason"))
        self.assertEqual(result["element"].kind, "input")

    def test_grounding_refuses_something_absent(self):
        result = self.grounding.ground(
            "click the Deploy to Production button", self.observation
        )

        self.assertFalse(result["found"])

    def test_grounding_prefers_an_interactive_target_for_a_click(self):
        result = self.grounding.ground("click Login", self.observation)

        self.assertTrue(result["found"])
        self.assertTrue(result["element"].interactive)

    def test_grounding_explains_its_choice(self):
        result = self.grounding.ground("click the Login button", self.observation)

        self.assertTrue(result["why"])
        self.assertTrue(result["candidates"])

    def test_no_hardcoded_coordinates_anywhere(self):
        """Section 17 forbids coordinate hardcoding; prove positions come from pixels."""

        moved = UIScreen(title="VisionTestApp").button("Login", 500, 90)
        observation = self.analyzer.analyze(moved.render()).data
        result = self.grounding.ground("click the Login button", observation)

        self.assertTrue(result["found"], result.get("reason"))
        self.assertGreater(result["element"].center[0], 400)
        self.assertLess(result["element"].center[1], 200)


@needs_pillow
class ChangeDetectionTests(unittest.TestCase):

    def test_identical_frames_report_no_change(self):
        image = login_screen().render()

        self.assertEqual(pixel_difference(image, image), 0.0)
        self.assertFalse(changed(image, image))

    def test_different_frames_report_change(self):
        before, after = state_pair()

        self.assertTrue(changed(before.render(), after.render()))

    def test_different_sizes_count_as_fully_changed(self):
        from PIL import Image

        self.assertEqual(
            pixel_difference(
                Image.new("RGB", (10, 10)), Image.new("RGB", (20, 20))
            ),
            1.0,
        )

    def test_missing_frame_does_not_raise(self):
        self.assertEqual(pixel_difference(None, None), 0.0)

    def test_changed_regions_locate_the_difference(self):
        before = UIScreen().button("Go", 100, 100)
        after = UIScreen().button("Go", 100, 100).button("Extra", 500, 400)
        regions = changed_regions(before.render(), after.render())

        self.assertTrue(regions)
        self.assertTrue(
            any(r.intersects(BBox(500, 400, 150, 46)) for r in regions),
            "the added button's region was not located",
        )

    def test_unchanged_screen_yields_no_regions(self):
        image = login_screen().render()

        self.assertEqual(changed_regions(image, image), [])


@needs_pillow
class StateComparisonTests(unittest.TestCase):

    def setUp(self):
        self.state = ScreenState()

        if not self.state.analyzer.ocr.available:
            self.skipTest("tesseract unavailable")

    def test_first_update_has_nothing_to_compare(self):
        self.state.update(login_screen().render())

        self.assertFalse(self.state.compare().changed)

    def test_identical_screens_report_no_structural_change(self):
        screen = login_screen()
        self.state.update(screen.render())
        self.state.update(screen.render())
        diff = self.state.compare()

        self.assertFalse(diff.changed, diff.summary())

    def test_an_added_element_is_detected(self):
        self.state.update(UIScreen().button("Go", 100, 100).render())
        self.state.update(
            UIScreen().button("Go", 100, 100).button("Extra", 400, 300).render()
        )
        diff = self.state.compare()

        self.assertTrue(diff.changed)
        self.assertTrue(diff.added)

    def test_a_removed_element_is_detected(self):
        self.state.update(
            UIScreen().button("Go", 100, 100).button("Extra", 400, 300).render()
        )
        self.state.update(UIScreen().button("Go", 100, 100).render())

        self.assertTrue(self.state.compare().removed)

    def test_a_moved_element_is_a_move_not_an_add_and_a_remove(self):
        self.state.update(UIScreen().button("Go", 100, 100).render())
        self.state.update(UIScreen().button("Go", 500, 380).render())
        diff = self.state.compare()

        self.assertTrue(diff.moved, diff.summary())
        self.assertFalse(diff.added)
        self.assertFalse(diff.removed)

    def test_pixel_ratio_is_recorded_on_the_diff(self):
        before, after = state_pair()
        self.state.update(before.render())
        self.state.update(after.render())

        self.assertGreater(self.state.compare().pixel_ratio, 0.0)

    def test_summary_describes_the_change(self):
        self.state.update(UIScreen().button("Go", 100, 100).render())
        self.state.update(
            UIScreen().button("Go", 100, 100).button("Extra", 400, 300).render()
        )

        self.assertIn("added", self.state.compare().summary())


@needs_pillow
class DocumentOCRTests(unittest.TestCase):
    """Document OCR only. Layout, tables and question answering are not built."""

    def setUp(self):
        self.ocr = OCRProvider()

        if not self.ocr.available:
            self.skipTest("tesseract unavailable")

        self.document = invoice()
        self.image = self.document.render()

    def test_document_text_is_read(self):
        text = self.ocr.read_text(self.image).data

        self.assertIn("ACME", text)
        self.assertIn("Invoice", text)

    def test_invoice_total_is_read_with_a_position(self):
        spans = self.ocr.phrases(self.ocr.read(self.image).data)
        totals = [s for s in spans if "2082.60" in s.text]

        self.assertTrue(totals, "the invoice total was not read")
        self.assertGreater(totals[0].bbox.area, 0)

    def test_read_position_matches_the_rendered_position(self):
        spans = self.ocr.phrases(self.ocr.read(self.image).data)
        totals = [s for s in spans if "2082.60" in s.text]
        truth = self.document.truth()["total"]

        self.assertLess(abs(totals[0].bbox.y - truth["y"]), 25)

    def test_dates_are_readable(self):
        text = self.ocr.read_text(self.image).data

        self.assertIn("March", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
