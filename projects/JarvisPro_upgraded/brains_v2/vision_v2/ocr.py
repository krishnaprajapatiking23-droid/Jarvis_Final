from pathlib import Path


def _configure_tesseract():
    """Set tesseract_cmd if not already set, using common Windows paths."""
    try:
        import pytesseract
    except ImportError:
        return None
    if hasattr(pytesseract, 'get_tesseract_version'):
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            pass
    for path in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]:
        if Path(path).exists():
            pytesseract.pytesseract.tesseract_cmd = path
            return True
    return False


_configured = _configure_tesseract()


def read(path):
    """Return OCR text from an image file, or '' on any failure."""
    if not path or not _configured:
        return ""

    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return ""

    try:
        image_path = Path(path)
        if not image_path.is_file():
            return ""
        image = Image.open(image_path)
        image.verify()
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text.strip() if text else ""
    except Exception:
        return ""
