"""Short notes on common particles, auxiliaries and て-form patterns, without a model call.

JMdict is no help here (it reads が as 画, "picture"), so the Read & translate tab explains
the grammar words it finds with these notes, keyed by the tokenizer's dictionary form.
"""

# Particles and auxiliary verbs, by dictionary form
GRAMMAR_NOTES = {
    "は": "topic marker: 'as for ...'; sets what the sentence is about",
    "が": "subject marker; between clauses, 'but'",
    "を": "marks the direct object of the verb",
    "に": "target, destination, time or place of existence: 'to, at, in'",
    "で": "place where an action happens, or means: 'at, by, with'",
    "へ": "direction: 'towards'",
    "と": "'and' between nouns; 'with' someone; marks a quotation",
    "も": "'also, too'; with a negative, 'not ... either'",
    "の": "links nouns ('s, of); also turns a clause into a noun",
    "から": "'from' (a place or time); after a clause, 'because'",
    "まで": "'until, as far as'",
    "より": "'than' in comparisons; 'from' in formal writing",
    "や": "'and (among others)' between nouns",
    "か": "question marker; between nouns, 'or'",
    "ね": "sentence end: seeks agreement, 'isn't it? right?'",
    "よ": "sentence end: tells the listener something new, 'you know'",
    "けど": "'but, although'",
    "けれど": "'but, although'",
    "て": "て-form: links actions or states, 'and (then)'",
    "ば": "conditional: 'if'",
    "たり": "lists example actions: 'do things like ...'",
    "ながら": "'while' doing (two actions at once)",
    "し": "lists reasons: 'and what's more'",
    "のに": "'even though, despite'",
    "ので": "'because, so' (softer than から)",
    "だけ": "'only, just'",
    "しか": "'only, nothing but' (always with a negative verb)",
    "など": "'and so on, etc.'",
    "くらい": "'about, approximately'; 'to the extent that'",
    "ぐらい": "'about, approximately'; 'to the extent that'",
    "ほど": "'to the extent of'; with a negative, 'not as ... as'",
    "って": "casual quote ('said that ...') or casual topic marker",
    "た": "past tense (or a completed action)",
    "だ": "plain 'is / am / are' (copula)",
    "です": "polite 'is / am / are' (copula)",
    "ます": "polite verb ending",
    "ない": "negative: 'not'",
    "ぬ": "negative: 'not' (old-fashioned; also ん)",
    "ん": "negative 'not' (in ません), or a contracted の",
    "たい": "'want to' do",
    "れる": "passive, potential ('can') or respectful form",
    "られる": "passive, potential ('can') or respectful form",
    "せる": "causative: 'make / let someone do'",
    "させる": "causative: 'make / let someone do'",
    "う": "volitional: 'let's ...', 'I'll ...'",
    "よう": "volitional: 'let's ...', 'I'll ...'; or 'seems like'",
    "らしい": "'seems, apparently' (from what I hear)",
    "そう": "'looks like' (after a stem) or 'I hear that'",
    "みたい": "'seems, like' (casual)",
    "まい": "negative intention: 'will not'",
}

# Verbs that make a pattern after the て-form, by dictionary form (kana and kanji)
TE_PATTERNS = {
    "いる": ("〜ている", "ongoing action ('is doing') or resulting state"),
    "ある": ("〜てある", "has been done (on purpose) and stays that way"),
    "しまう": ("〜てしまう", "do completely; or end up doing (often with regret)"),
    "みる": ("〜てみる", "try doing and see"),
    "おく": ("〜ておく", "do in advance, or leave as it is"),
    "くる": ("〜てくる", "come to do; start to; go and do and come back"),
    "いく": ("〜ていく", "go on doing; do and go"),
    "あげる": ("〜てあげる", "do for someone else"),
    "くれる": ("〜てくれる", "someone does for me / us"),
    "もらう": ("〜てもらう", "have someone do for me"),
    "くださる": ("〜てください", "please do (polite request)"),
    "ほしい": ("〜てほしい", "want someone to do"),
}
for kana, kanji in [("いる", "居る"), ("みる", "見る"), ("おく", "置く"), ("くる", "来る"), ("いく", "行く"),
                    ("あげる", "上げる"), ("くれる", "呉れる"), ("もらう", "貰う"), ("くださる", "下さる"),
                    ("しまう", "仕舞う"), ("ある", "有る"), ("ほしい", "欲しい")]:
    TE_PATTERNS[kanji] = TE_PATTERNS[kana]
