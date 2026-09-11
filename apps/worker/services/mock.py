from models import ClipCandidate


def mock_clips(max_clips: int) -> list[ClipCandidate]:
    clips = [
        ClipCandidate(
            start=83.2, end=124.8,
            title="The mistake that changed everything",
            hook="The biggest mistake I made early on was optimizing for money instead of leverage.",
            score=94,
            reasons=["strong hook", "personal story", "clear payoff", "standalone"],
        ),
        ClipCandidate(
            start=611.4, end=655.7,
            title="Why most people quit too early",
            hook="People think progress is linear, but almost all the upside arrives after the boring part.",
            score=91,
            reasons=["contrarian insight", "relatable", "high retention", "clean ending"],
        ),
        ClipCandidate(
            start=1380.1, end=1428.5,
            title="The AI advantage nobody talks about",
            hook="AI doesn't just make experts faster — it changes what a beginner can attempt.",
            score=88,
            reasons=["timely topic", "clear thesis", "shareable", "educational"],
        ),
        ClipCandidate(
            start=954.0, end=986.3,
            title="A better way to think about risk",
            hook="The safest-looking decision can be the riskiest one if it locks you into the wrong path.",
            score=85,
            reasons=["counterintuitive", "concise", "memorable line", "standalone"],
        ),
        ClipCandidate(
            start=1711.5, end=1750.2,
            title="The question I ask before saying yes",
            hook="Before I say yes to anything, I ask whether I'd still want to do it if nobody could see it.",
            score=82,
            reasons=["practical", "quotable", "self-contained", "clean hook"],
        ),
        ClipCandidate(
            start=402.8, end=436.4,
            title="Stop copying successful people",
            hook="Copying someone's tactics without their context is one of the fastest ways to waste a year.",
            score=79,
            reasons=["bold opener", "useful", "short", "clear takeaway"],
        ),
    ]
    return clips[:max_clips]
