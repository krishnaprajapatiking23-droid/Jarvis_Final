from pathlib import Path
class OCRResult:
 def __init__(self,ok,text='',error='',backend='tesseract'):self.ok=ok;self.text=text;self.error=error;self.backend=backend
 def report(self):return vars(self)
def read(image_path):
 path=Path(image_path)
 if not path.is_file():return OCRResult(False,error='invalid image path')
 try:
  from PIL import Image
  import pytesseract
  image=Image.open(path);image.verify();image=Image.open(path)
  text=pytesseract.image_to_string(image).strip();return OCRResult(True,text,backend='tesseract')
 except ImportError as e:return OCRResult(False,error='OCR dependency unavailable: '+str(e))
 except Exception as e:return OCRResult(False,error=f'OCR failure: {type(e).__name__}: {e}')
def read_text(image_path):
    """Return OCR text from an image file, or '' on any failure."""
    if not image_path:
        return ""
    result = read(image_path)
    if not result.ok:
        return ""
    return result.text
