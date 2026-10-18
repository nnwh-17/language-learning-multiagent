from dataclasses import dataclass, field
 
from llma.models.analysis import AnalysisResult
from llma.models.examples import ExampleSentence
 
 
@dataclass
class State:
    """Shared by all supervisor tools for the whole chat.
 
    Tools keep full data here and return only short summaries to the
    supervisor, so big results don't pass through the LLM's context.
    """
 
    analysis: AnalysisResult | None = None
    examples: dict[str, list[ExampleSentence]] = field(default_factory=dict)
 