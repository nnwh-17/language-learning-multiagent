from pydantic import BaseModel, Field
 
 
class ExampleSentence(BaseModel):
    japanese: str = Field(description="Natural Japanese sentence using the target word or pattern")
    reading: str = Field(description="Full sentence in hiragana")
    english: str = Field(description="Natural English translation")
 
 
class GeneratedExamples(BaseModel):
    # Wrapped in an object (not a bare list) so every model handles it reliably
    examples: list[ExampleSentence]