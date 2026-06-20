# NO LLM IN THIS MODULE. Pure Python only.
# This is where you enforce what models can't reliably do: count, measure, detect.

import re


class LinkedInQAChecker:

    # ── Python-only methods ──────────────────────────────────────────────

    def count_words(self, text: str) -> int:
        # Strip hashtags before counting, then len(text.split())
        clean = ' '.join(line for line in text.split('\n') if not line.strip().startswith('#'))
        return len(clean.split())

    def count_hashtags(self, text: str) -> int:
        # Count lines or tokens starting with #
        return len(re.findall(r'#\w+', text))

    def get_first_line(self, text: str) -> str:
        # Return first non-empty line
        for line in text.split('\n'):
            if line.strip():
                return line.strip()
        return ""

    def count_words_in_line(self, line: str) -> int:
        return len(line.split())

    def get_long_lines(self, text: str, max_words: int = 12) -> list[str]:
        # Return all lines (excluding hashtag lines) that exceed max_words
        violations = []
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                if self.count_words_in_line(stripped) > max_words:
                    violations.append(stripped)
        return violations

    def has_banned_opener(self, text: str) -> bool:
        banned_openers = [
            "in today's", "i'm excited", "i'm thrilled", "thrilled to",
            "humbled to", "it's important", "let's dive", "in this fast"
        ]
        first_line = self.get_first_line(text).lower()
        return any(first_line.startswith(opener) for opener in banned_openers)

    def has_banned_words(self, text: str) -> list[str]:
        banned = [
            'delve', 'leverage', 'realm', 'tapestry', 'synergy',
            'seamlessly', 'humbled to announce', 'thrilled to share',
            'excited to share', 'game-changer', 'revolutionary',
            'cutting-edge', 'utilize', 'navigate', 'moreover', 'furthermore'
        ]
        text_lower = text.lower()
        return [word for word in banned if word in text_lower]

    def count_cta_signals(self, text: str) -> int:
        # Rough heuristic: count question marks + "save this" + "follow" + "repost"
        signals = len(re.findall(r'\?', text))
        soft_asks = len(re.findall(r'\b(save this|follow me|repost|share this)\b', text.lower()))
        return signals + soft_asks

    def has_wall_of_text(self, text: str) -> bool:
        # True if any paragraph (consecutive non-empty lines) is longer than 3 lines
        paragraphs = text.split('\n\n')
        for para in paragraphs:
            lines = [l for l in para.split('\n') if l.strip()]
            if len(lines) > 3:
                return True
        return False

    # ── Main QA method ───────────────────────────────────────────────────

    def check(self, post_text: str) -> dict:
        """
        Run all Python checks. Returns:
        {
            word_count: int,
            hashtag_count: int,
            first_line: str,
            first_line_word_count: int,
            long_lines: list[str],
            has_banned_opener: bool,
            banned_words_found: list[str],
            cta_signal_count: int,
            has_wall_of_text: bool,
            passes_word_count: bool,        # 600 <= word_count <= 800
            passes_hashtag_count: bool,     # 3 <= hashtag_count <= 5
            passes_line_length: bool,       # long_lines is empty
            passes_hook: bool,              # not has_banned_opener
            passes_banned_words: bool,      # banned_words_found is empty
            passes_cta: bool,               # cta_signal_count == 1
            passes_white_space: bool,       # not has_wall_of_text
            overall_pass: bool              # all passes_* are True
        }
        """
        word_count = self.count_words(post_text)
        hashtag_count = self.count_hashtags(post_text)
        first_line = self.get_first_line(post_text)
        long_lines = self.get_long_lines(post_text)
        banned_opener = self.has_banned_opener(post_text)
        banned_words = self.has_banned_words(post_text)
        cta_count = self.count_cta_signals(post_text)
        wall = self.has_wall_of_text(post_text)

        passes = {
            "passes_word_count":    600 <= word_count <= 800,
            "passes_hashtag_count": 3 <= hashtag_count <= 5,
            "passes_line_length":   len(long_lines) == 0,
            "passes_hook":          not banned_opener,
            "passes_banned_words":  len(banned_words) == 0,
            "passes_cta":           cta_count == 1,
            "passes_white_space":   not wall,
        }

        return {
            "word_count":           word_count,
            "hashtag_count":        hashtag_count,
            "first_line":           first_line,
            "first_line_word_count": self.count_words_in_line(first_line),
            "long_lines":           long_lines,
            "has_banned_opener":    banned_opener,
            "banned_words_found":   banned_words,
            "cta_signal_count":     cta_count,
            "has_wall_of_text":     wall,
            **passes,
            "overall_pass":         all(passes.values()),
        }
