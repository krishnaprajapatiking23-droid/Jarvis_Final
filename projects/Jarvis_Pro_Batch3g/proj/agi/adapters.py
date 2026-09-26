from __future__ import annotations
from dataclasses import dataclass,field
from typing import Any
@dataclass
class Percept:modality:str;text:str;observations:list[dict]=field(default_factory=list);confidence:float=.5;errors:list[str]=field(default_factory=list)
class PerceptionAdapter:
 def text(self,text):return Percept('text',str(text),[],1.0)
 def voice(self,transcript,partial=False,confidence=.7):return Percept('voice',str(transcript),[{'partial':partial}],confidence,[] if transcript else ['silence'])
 def vision(self,ocr_text='',objects=None,layout=None,model_description=''):
  obs=[{'type':'ocr','text':ocr_text},{'type':'objects','items':objects or []},{'type':'layout','items':layout or []}]
  text=model_description or ocr_text
  return Percept('vision',text,obs,.8 if model_description else .45,['OCR-only; advanced visual understanding unavailable'] if not model_description else [])
adapters=PerceptionAdapter()
