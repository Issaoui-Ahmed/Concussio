import unittest
from unittest.mock import patch

from core.response_format import (
    DISCLAIMERS,
    EMERGENCY_TEXT,
    EVIDENCE_URL,
    VAUGHAN_DOI,
    format_response,
    strip_internal_citations,
)
from core.response_resources import _bundled_tools, tools_from_corpus
from core.response_resources import LINK_RE


TEACHER_RESPONSE = """**Summary:**
Support a gradual return to school.

**Living Guidelines Recommendations:**
- Offer quiet breaks (Recommendation 12.1; Level of Evidence: B).
- Reduce workload (Recommendation 12.1a; Level of Evidence: C).
- Use Tool 12.2 - Template-for-Concussion-Team_Letter-to-the-Child_Adolescent_School.
- Watch for red flags including seizure or loss of consciousness; contact the caregiver.

**Information From the Literature:**
Earlier return was associated with lower symptom burden (Vaughan et al., 2023).

copilot knowledge base citations - [3]
"""


class ResponseFormatTests(unittest.TestCase):
    def setUp(self):
        self.tools = _bundled_tools()
        self.catalog_patch = patch("core.response_format.response_tools", return_value=self.tools)
        self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)

    def test_teacher_review_regression(self):
        answer = format_response(TEACHER_RESPONSE, "Teacher", "en")
        body, footer = answer.split("**Sources:**")
        self.assertNotIn("copilot", answer)
        self.assertNotIn("Living Guidelines Recommendations", answer)
        visible_body = LINK_RE.sub(lambda match: match[1], body)
        self.assertNotIn("Template-for-", visible_body)
        self.assertIn("[Tool 12.2: Letter of Accommodation from the Concussion Care Team to the School]", body)
        self.assertNotIn("Recommendation 12.1", body)
        self.assertNotIn("Vaughan", body)
        self.assertIn("[Recommendation 12.1](https://pedsconcussion.com/domain/12/)", footer)
        self.assertIn("Level of Evidence: B", footer)
        self.assertIn("Association between early return to school", footer)
        self.assertIn(VAUGHAN_DOI, footer)
        self.assertIn(EVIDENCE_URL, footer)
        self.assertIn("A = Strong research evidence", footer)
        self.assertIn(EMERGENCY_TEXT["en"], body)
        self.assertTrue(answer.endswith(DISCLAIMERS["en"][False]))
        self.assertLess(answer.index("**Sources:**"), answer.index("Level of Evidence legend"))

    def test_clinician_keeps_inline_citations_and_full_references(self):
        answer = format_response(TEACHER_RESPONSE, "Healthcare Professional", "en")
        body = answer.split("**Sources:**")[0]
        self.assertIn("[Recommendation 12.1]", body)
        self.assertIn("(Vaughan et al., 2023)", body)
        self.assertIn("A = Consistent, good-quality, patient-oriented evidence", answer)
        self.assertIn("C = Consensus, usual practice, opinion, or weaker-level evidence", answer)
        self.assertIn(VAUGHAN_DOI, answer)
        self.assertTrue(answer.endswith(DISCLAIMERS["en"][True]))

    def test_all_roles_and_aliases_get_correct_final_disclaimer(self):
        for role in ("Teacher", "Parent or Caregiver", "parent", "Youth", "Coach", "patient", None):
            with self.subTest(role=role):
                self.assertTrue(format_response("Hello!", role, "en").endswith(DISCLAIMERS["en"][False]))
        self.assertTrue(format_response("Hello!", "doctor", "en").endswith(DISCLAIMERS["en"][True]))

    def test_no_evidence_legend_or_unused_paper_on_greeting(self):
        answer = format_response("Hello!", "Teacher", "en")
        self.assertNotIn("Level of Evidence legend", answer)
        self.assertNotIn("Sources:", answer)
        self.assertNotIn(VAUGHAN_DOI, answer)

    def test_internal_inline_marker_does_not_delete_medical_advice(self):
        text = "Offer breaks copilot knowledge base citations - [3]. Contact the caregiver if symptoms worsen."
        answer = strip_internal_citations(text)
        self.assertIn("Offer breaks", answer)
        self.assertIn("Contact the caregiver if symptoms worsen.", answer)
        self.assertNotIn("copilot", answer)
        self.assertNotIn("[3]", answer)

    def test_internal_block_and_file_search_results_are_hidden(self):
        text = """Give quiet breaks.
**copilot knowledge base citations:**
[3] internal-source.txt

Call the caregiver.
**File Search Results (if any):**
- Tool 12.2 - raw-file.txt
- Vaughan et al. Early return to school and symptoms, 2023.txt
**Sources:**
- [Recommendation 12.1](https://pedsconcussion.com/domain/12/)
"""
        answer = format_response(text, "Teacher", "en")
        self.assertIn("Call the caregiver.", answer)
        self.assertNotIn("File Search", answer)
        self.assertNotIn(".txt", answer)
        self.assertIn("[Recommendation 12.1]", answer)

    def test_real_numbered_bibliography_is_preserved(self):
        text = "A finding [1].\n\n**References:**\n[1] Smith, J. (2024). A study. Journal, 1, 1–4. [DOI](https://doi.org/10.1234/example)"
        answer = format_response(text, "Teacher", "en")
        self.assertNotIn("[1]", answer.split("**Sources:**")[0])
        self.assertIn("Smith, J. (2024). A study.", answer)
        self.assertIn("https://doi.org/10.1234/example", answer)

    def test_repeated_and_grouped_recommendations_are_all_linked(self):
        answer = format_response("Recommendations 12.1, 12.1a and 6.1. Repeat Recommendation 12.1.", "doctor", "en")
        self.assertEqual(answer.count("[Recommendation 12.1](https://pedsconcussion.com/domain/12/)"), 2)
        self.assertIn("[Recommendation 12.1a](https://pedsconcussion.com/domain/12/)", answer)
        self.assertIn("[Recommendation 6.1](https://pedsconcussion.com/domain/6/)", answer)
        self.assertNotIn("[[", answer)

    def test_existing_recommendation_anchor_is_preserved(self):
        link = "[Recommendation 2.3c](https://pedsconcussion.com/domain/2/#rec-614)"
        answer = format_response(link, "doctor", "en")
        self.assertIn(link, answer)
        self.assertNotIn("[[", answer)

    def test_tool_number_outside_link_is_not_duplicated(self):
        tool = self.tools["12.2"]
        answer = format_response(f"Tool 12.2: [Template letter]({tool.url})", "doctor", "en")
        self.assertEqual(answer.count("Tool 12.2"), 1)
        self.assertIn(f"[{tool.label}]({tool.url})", answer)

    def test_bare_tool_with_public_title_is_not_duplicated(self):
        tool = self.tools["12.2"]
        answer = format_response(f"Use Tool 12.2: Template: {tool.title}.", "doctor", "en")
        self.assertEqual(answer.count(tool.title), 1)
        self.assertIn(f"[{tool.label}]({tool.url}).", answer)

    def test_filename_label_of_known_document_gets_public_title(self):
        tool = self.tools["12.2"]
        answer = format_response(f"[Tool-12.2-Template-for-Concussion-Team_Letter.pdf]({tool.url})", "doctor", "en")
        self.assertIn(f"[{tool.label}]", answer)
        self.assertNotIn("[Tool-12.2-", answer)

    def test_general_author_year_citations_move_to_sources(self):
        text = "Offer breaks (Smith, 2024). Smith et al. (2024) found an association. Keep adjustments (such as quiet breaks)."
        answer = format_response(text, "Teacher", "en")
        body, sources = answer.split("**Sources:**")
        self.assertNotIn("Smith", body)
        self.assertIn("The study found an association.", body)
        self.assertIn("(such as quiet breaks)", body)
        self.assertIn("Smith", sources)
        self.assertNotIn("doi.org", answer)  # No fabricated metadata for an unknown paper.

    def test_medical_instruction_sharing_citation_parentheses_stays_in_body(self):
        text = "Adjust the plan (contact the caregiver if symptoms worsen; Recommendation 12.1; Level of Evidence: B)."
        answer = format_response(text, "Teacher", "en")
        body = answer.split("**Sources:**")[0]
        self.assertIn("contact the caregiver if symptoms worsen", body)
        self.assertNotIn("Recommendation 12.1", body)

    def test_emergency_wording_is_present_for_every_audience(self):
        for role in ("Teacher", "Parent or Caregiver", "Youth", "Healthcare Professional"):
            with self.subTest(role=role):
                answer = format_response("Red flags: worsening headache. Contact the caregiver.", role, "en")
                self.assertIn(EMERGENCY_TEXT["en"], answer)
                self.assertEqual(answer.count(EMERGENCY_TEXT["en"]), 1)

    def test_french_footer_and_language_detection(self):
        text = "**Résumé :**\nVous pouvez adapter les tâches.\n\nRecommandation 12.1 (Niveau de preuve : B). Signes d’alerte : convulsions."
        answer = format_response(text, "Teacher")
        self.assertIn("Légende des niveaux de preuve", answer)
        self.assertIn("A = Données de recherche solides", answer)
        self.assertIn(EMERGENCY_TEXT["fr"], answer)
        self.assertTrue(answer.endswith(DISCLAIMERS["fr"][False]))

    def test_footer_is_idempotent_for_both_audiences(self):
        for role in ("Teacher", "Healthcare Professional"):
            with self.subTest(role=role):
                once = format_response(TEACHER_RESPONSE, role, "en")
                twice = format_response(once, role, "en")
                self.assertEqual(once, twice)

    def test_sources_after_legend_are_reordered(self):
        text = """Offer breaks. Level of Evidence: B
**Level of Evidence legend:**
- A = Old wording
**Sources:**
- Recommendation 12.1
"""
        answer = format_response(text, "Teacher", "en")
        self.assertNotIn("Old wording", answer)
        self.assertLess(answer.index("**Sources:**"), answer.index("Level of Evidence legend"))

    def test_sources_subheadings_stay_in_sources_and_short_evidence_levels_get_legend(self):
        text = """Offer breaks.
**Sources:**
**Living Guideline Recommendations (with Levels of Evidence):**
- Recommendation 12.1: stepwise plan. **Level B**
**Tools:**
- Tool 12.2
"""
        answer = format_response(text, "Teacher", "en")
        body, sources = answer.split("**Sources:**")
        self.assertNotIn("Level B", body)
        self.assertIn("[Recommendation 12.1]", sources)
        self.assertIn("Level of Evidence legend", sources)

    def test_catalog_uses_published_titles_not_url_slugs(self):
        tools = tools_from_corpus("* Tool 12.2: [Template: Letter of Accommodation](https://example.com/Tool-12.2-raw_filename.pdf)")
        self.assertEqual(tools["12.2"].title, "Letter of Accommodation from the Concussion Care Team to the School")

    def test_catalog_does_not_attribute_unrelated_link_to_preceding_tool(self):
        tools = tools_from_corpus("Tool 12.1: [Classroom supports](https://example.com/tool-12-1.pdf) and [other resource](https://example.com/other)")
        self.assertEqual(tools["12.1"].url, "https://example.com/tool-12-1.pdf")


class ResponseIntegrationTests(unittest.TestCase):
    def test_canned_chat_path_includes_disclaimer(self):
        from api._chat import ChatRequest, _answer
        answer = _answer(ChatRequest(message="Hello", user_type="Teacher", lang="en"))
        self.assertEqual(answer["routed"], "greeting")
        self.assertTrue(answer["answer"].endswith(DISCLAIMERS["en"][False]))

    def test_smalltalk_chat_path_includes_disclaimer(self):
        from api._chat import ChatRequest, _answer
        with patch("api._chat.generate_smalltalk_reply", return_value="Happy to help!"):
            answer = _answer(ChatRequest(message="How are you?", user_type="Teacher", lang="en"))
        self.assertTrue(answer["answer"].endswith(DISCLAIMERS["en"][False]))

    def test_run_override_preserves_published_corpus_and_formats_answer(self):
        from core.fuelix_chat import generate_fuelix_answer
        with (
            patch("core.fuelix_chat.resolve_assistant_id", return_value="test-assistant"),
            patch("core.fuelix_chat._assistant_instructions", return_value="PUBLISHED CORPUS AND SAFEGUARDS"),
            patch("core.fuelix_chat._attempt_fuelix_answer", return_value={
                "answer": "Offer breaks (Recommendation 12.1; Level of Evidence: B).",
                "thread_id": "test-thread", "run_id": "test-run", "run_status": "completed",
            }) as run,
            patch("core.response_format.response_tools", return_value=_bundled_tools()),
        ):
            result = generate_fuelix_answer("Help with school headaches", "Teacher", "en")
        instructions = run.call_args.kwargs["instructions"]
        self.assertTrue(instructions.startswith("PUBLISHED CORPUS AND SAFEGUARDS"))
        self.assertIn("RESPONSE PRESENTATION", instructions)
        self.assertIn("Sources", result["answer"])
        self.assertTrue(result["answer"].endswith(DISCLAIMERS["en"][False]))

    def test_static_prompts_use_new_heading_and_link_rules(self):
        from core.prompts import build_fuelix_assistant_instructions
        for role in ("Teacher", "Healthcare Professional"):
            with self.subTest(role=role):
                instructions = build_fuelix_assistant_instructions(role, recommendations_markdown="TEST CORPUS")
                self.assertNotIn("Living Guidelines Recommendations", instructions)
                self.assertNotIn("don`t use links", instructions)
                self.assertIn("full reference in Sources", instructions)
                self.assertIn("TEST CORPUS", instructions)


if __name__ == "__main__":
    unittest.main()
