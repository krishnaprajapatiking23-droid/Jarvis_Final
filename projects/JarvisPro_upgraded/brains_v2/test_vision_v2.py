from brains_v2.vision_v2 import see

# BUG FIX: the screenshot helper returns a result dict, not a path, so
# passing it straight to the OCR reader raised
# TypeError: argument should be a str or an os.PathLike object ... not 'dict'.
# This unwraps whichever shape the helper returned.


def _image_path(value):
    """Accept a path, or a result dict that carries one."""
    if isinstance(value, dict):
        for key in ("path", "file", "filename", "image", "screenshot"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        raise ValueError("no image path in %r" % (sorted(value),))
    return value




result = see()

print()

print(result["ocr"])

print()

print(result["analysis"])