# The data shape for ONE flashcard, independent of where it came from.
# Keeping this separate means the card builder doesn't care whether a card
# came from a vocab item, a grammar point, or (later) an example sentence.
 
from pydantic import BaseModel, Field
 
 
class AnkiCard(BaseModel):
    front: str = Field(description="Text shown on the front of the card")
    back: str = Field(description="Text shown on the back. May contain <br> for line breaks")
    tags: list[str] = Field(default_factory=list, description="Anki tags, e.g. ['vocab', 'N4']")
 