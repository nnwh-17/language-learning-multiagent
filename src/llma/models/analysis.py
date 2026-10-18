'''
Defines the "shape" of the data the analyzer agent must return. PydanticAI converts these classes into a schema and sends it to the model, then validates the model's answer against it. If the answer doesn't fit (missing field, wrong type), PydanticAI asks the model to try again.
'''

from pydantic import BaseModel, Field
# BaseModel: the base class for all Pydantic data models.
# Field: lets us attach a description (and defaults) to each field.

class VocabItem(BaseModel):
    """One vocabulary word that will become a flashcard."""
    
    # The description text is included in the schema the model sees, so it works like a mini-instruction for that specific field.
    word: str = Field(description="Dictionary form of the word, as written in Japanese (e.g. 食べる, not 食べました)")
    reading: str = Field(description="Reading in hiragana")
    meaning: str = Field(description="Concise English meaning")
    
    # The model may leave it out when it isn't confident about the jlpt level.
    jlpt_level: str | None = Field(
        default=None,
        description="One of N5, N4, N3, N2, N1. Use null if you are not confident.",
    )

class GrammarPoint(BaseModel):
    """One grammar pattern found in the text."""
    
    pattern: str = Field(description="The grammar pattern in its base form (e.g. ～ながら, ～つもり)")
    
    explanation: str = Field(description="Short English explanation of meaning and usage")
    
    # Asking for the exact fragment lets you check the model didn't make it up:
    # you can search for this string in the original text.
    example_from_text: str = Field(description="The exact sentence or fragment from the input text that uses it")

class AnalysisResult(BaseModel):
    """The full output of the analyzer: everything extracted from one text.
 
    This is the class we pass to the agent as output_type.
    """
 
    vocab: list[VocabItem]
    grammar: list[GrammarPoint]