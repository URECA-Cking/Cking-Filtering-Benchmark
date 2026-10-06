import unittest

from src.rules.decision import BLOCK, PASS, decide
from src.rules.patterns import PatternHits
from src.rules.profanity import ProfanityHits

NO_PATTERNS = PatternHits(spam=(), privacy=())
NO_PROFANITY = ProfanityHits(words=())


class DecideTest(unittest.TestCase):
    def test_아무_신호도_없으면_통과한다(self):
        decision = decide(False, NO_PATTERNS, NO_PROFANITY)
        self.assertEqual(decision.action, PASS)
        self.assertEqual(decision.reasons, ())

    def test_모델이_위반으로_판정하면_막는다(self):
        decision = decide(True, NO_PATTERNS, NO_PROFANITY)
        self.assertEqual((decision.action, decision.reasons), (BLOCK, ("model",)))

    def test_모델_근거_이름을_바꿀_수_있다(self):
        decision = decide(True, NO_PATTERNS, NO_PROFANITY, model_reason="classifier")
        self.assertEqual((decision.action, decision.reasons), (BLOCK, ("classifier",)))

    def test_욕설_사전에만_걸려도_막는다(self):
        decision = decide(False, NO_PATTERNS, ProfanityHits(words=("시발",)))
        self.assertEqual((decision.action, decision.reasons), (BLOCK, ("profanity:시발",)))

    def test_개인정보가_걸리면_막는다(self):
        decision = decide(False, PatternHits(spam=(), privacy=("phone",)), NO_PROFANITY)
        self.assertEqual((decision.action, decision.reasons), (BLOCK, ("privacy:phone",)))

    def test_링크만_있으면_막지_않는다(self):
        decision = decide(False, PatternHits(spam=("link",), privacy=()), NO_PROFANITY)
        self.assertEqual(decision.action, PASS)

    def test_링크와_유도_문구가_함께_있으면_둘_다_근거로_남기고_막는다(self):
        decision = decide(False, PatternHits(spam=("link", "solicit"), privacy=()), NO_PROFANITY)
        self.assertEqual((decision.action, decision.reasons), (BLOCK, ("spam:link", "spam:solicit")))

    def test_여러_신호가_겹치면_모두_근거로_남긴다(self):
        decision = decide(True, PatternHits(spam=("flood",), privacy=("email",)), ProfanityHits(words=("병신",)))
        self.assertEqual(
            decision.reasons,
            ("model", "profanity:병신", "privacy:email", "spam:flood"),
        )


if __name__ == "__main__":
    unittest.main()
