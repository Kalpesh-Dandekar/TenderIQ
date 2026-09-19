import hashlib
import json

import pytest

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference
from app.models.blueprint_evidence import SemanticRequestCategory
from app.models.document_intelligence import CandidateEvidence, CandidateType, LocalCandidate, ResolutionCapability
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.models.hybrid_blueprint import GeminiWorkUnit, GroundedContext, WorkUnitReason
from app.services.commercial_financial_blueprint import (
    CommercialFinancialBlueprintService, CommercialFinancialSmokeTestError, GoogleCommercialFinancialProvider,
    build_commercial_financial_generation_config, commercial_financial_response_json_schema,
    parse_commercial_financial_response, select_commercial_financial_request, serialize_commercial_financial_request,
    _canonical_variable_role,
)
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.evidence_packager import BlueprintEvidencePackager
from app.services.hybrid_blueprint import build_local_draft

FINANCIAL = "Financial Score = (Lowest Bid Value/Bid Value of Bidder) *100"
CONSOLIDATED = "Consolidated Bid Score = Technical Score * 0.7 + Financial Score*0.3"


def document(*texts):
    pages = [ExtractedPage(page_number=i, text=t, character_count=len(t), word_count=len(t.split())) for i, t in enumerate(texts, 1)]
    raw = "".join(texts).encode()
    return ExtractedDocument(filename="commercial.pdf", sha256=hashlib.sha256(raw).hexdigest(), page_count=len(pages),
        total_characters=sum(len(t) for t in texts), total_words=sum(len(t.split()) for t in texts), text_pages=len(pages),
        empty_pages=0, assessment=ExtractionAssessment.TEXT_EXTRACTABLE, metadata=PdfMetadata(), pages=pages)


def plan(*texts, review_indexes=None):
    review_indexes = review_indexes or set(); source = document(*texts)
    draft = build_local_draft(LocalDocumentIntelligenceService().analyze(source)); units = []
    for i, text in enumerate(texts, 1):
        section = f"FIN-SECTION-{i}"
        candidate = LocalCandidate(candidate_id=f"FIN-LOCAL-{i}", candidate_type=CandidateType.SEMANTIC,
            category=RequirementCategory.FINANCIAL, raw_text=text, normalized=NormalizedRequirement(),
            evidence=[CandidateEvidence(source_reference=SourceReference(page_number=i, section="FINANCIAL EVALUATION", excerpt=text[:600]), section_id=section)],
            confidence=.6, ambiguous=i in review_indexes, ambiguity_reason="Needs review" if i in review_indexes else None,
            resolution_capability=ResolutionCapability.REVIEW_REQUIRED if i in review_indexes else ResolutionCapability.LLM_REQUIRED)
        units.append(GeminiWorkUnit(work_unit_id=f"FIN-WU-{i}", prompt_version="hybrid-v2", document_sha256=source.sha256,
            reason=WorkUnitReason.UNRESOLVED_CANDIDATES, section_ids=[section], page_numbers=[i],
            context=[GroundedContext(page_number=i, section_id=section, heading="FINANCIAL EVALUATION", text=text)], candidates=[candidate]))
    return BlueprintEvidencePackager().package(draft, units, source.total_characters)


def handle_for(value, phrase):
    return next(record.handle for record in select_commercial_financial_request(value).records if phrase.casefold() in record.text.casefold())


def rule(handle, **changes):
    value = {"kind":"FINANCIAL_SCORE_FORMULA", "title":"Financial Score", "description":FINANCIAL,
        "mandatory":None, "formula_expression":"FINANCIAL_SCORE=(LOWEST_VALID_BID/BIDDER_BID_VALUE)*100",
        "formula_variables":["FINANCIAL_SCORE","LOWEST_VALID_BID","BIDDER_BID_VALUE"], "formula_semantics":"RATIO_PERCENT",
        "formula_multiplier":100, "technical_weight_percent":None, "financial_weight_percent":None,
        "percentage_value":None, "money_value":None, "currency":None, "operator":None, "unit":None,
        "expected_evidence":[], "evidence_ids":[handle], "requires_review":False, "review_reason":None}
    value.update(changes); return value


def payload(*rules): return json.dumps({"rules":list(rules)})


class FakeProvider:
    model="fake-gemini"
    def __init__(self, response, metadata=None, error=None): self.response=response; self.metadata=metadata or {}; self.error=error; self.calls=0
    def generate(self, prompt):
        self.calls += 1
        if self.error: raise self.error
        return self.response, self.metadata


class RecordingModels:
    def __init__(self, text): self.text=text; self.calls=[]
    def generate_content(self, **kwargs):
        self.calls.append(kwargs); return type("Response",(),{"text":self.text,"response_id":"mock-id","usage_metadata":None})()


def test_only_commercial_financial_request_is_selected():
    assert select_commercial_financial_request(plan(FINANCIAL)).category == SemanticRequestCategory.COMMERCIAL_FINANCIAL


def test_other_category_cannot_execute():
    value=plan(FINANCIAL); value.semantic_requests[0]=value.semantic_requests[0].model_copy(update={"category":SemanticRequestCategory.TECHNICAL})
    provider=FakeProvider(payload())
    with pytest.raises(CommercialFinancialSmokeTestError): CommercialFinancialBlueprintService(provider).execute(value)
    assert provider.calls == 0


def test_unsupported_handle_is_rejected():
    result=CommercialFinancialBlueprintService(FakeProvider(payload(rule("E9999")))).execute(plan(FINANCIAL))
    assert result.accepted_count == 0 and result.unsupported_evidence_handle_count == 1


def test_provenance_restoration():
    value=plan(FINANCIAL); item=CommercialFinancialBlueprintService(FakeProvider(payload(rule(handle_for(value,"Lowest"))))).execute(value).rules[0]
    assert item.source_pages == [1] and item.source_section_ids == ["FIN-SECTION-1"] and item.source_work_unit_ids == ["FIN-WU-1"]


def test_stable_ids_are_deterministic():
    value=plan(FINANCIAL); data=payload(rule(handle_for(value,"Lowest")))
    assert CommercialFinancialBlueprintService(FakeProvider(data)).execute(value).rules[0].rule_id == CommercialFinancialBlueprintService(FakeProvider(data)).execute(value).rules[0].rule_id


def test_financial_formula_is_machine_readable():
    value=plan(FINANCIAL); item=CommercialFinancialBlueprintService(FakeProvider(payload(rule(handle_for(value,"Lowest"))))).execute(value).rules[0]
    assert item.formula_expression == "FINANCIAL_SCORE=(LOWEST_VALID_BID/BIDDER_BID_VALUE)*100"
    assert item.formula_multiplier == 100


def test_formula_variables_remain_distinct():
    value=plan(FINANCIAL); item=CommercialFinancialBlueprintService(FakeProvider(payload(rule(handle_for(value,"Lowest"))))).execute(value).rules[0]
    assert {v.value for v in item.formula_variables} == {"FINANCIAL_SCORE","LOWEST_VALID_BID","BIDDER_BID_VALUE"}


@pytest.mark.parametrize(("alias","expected"),[
    ("Lowest Bid Value","LOWEST_VALID_BID"), ("Lowest Valid Bid","LOWEST_VALID_BID"),
    ("Bid Value of Bidder","BIDDER_BID_VALUE"), ("Bidder Bid Value","BIDDER_BID_VALUE"),
    ("Consolidated Bid Score","CONSOLIDATED_SCORE"), ("Consolidated Score","CONSOLIDATED_SCORE"),
])
def test_formula_variable_aliases_canonicalize_narrowly(alias,expected):
    assert _canonical_variable_role(alias).value == expected


def test_correct_financial_inputs_without_output_variable_do_not_review():
    value=plan(FINANCIAL); item=rule(handle_for(value,"Lowest"),formula_variables=["LOWEST_VALID_BID","BIDDER_BID_VALUE"])
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert not result.requires_review


def test_multiplier_is_not_threshold_or_percentage_rule():
    value=plan(FINANCIAL); item=CommercialFinancialBlueprintService(FakeProvider(payload(rule(handle_for(value,"Lowest"))))).execute(value).rules[0]
    assert item.formula_multiplier == 100 and item.percentage_value is None and item.operator is None


def consolidated_rule(handle, **changes):
    value = dict(kind="WEIGHTED_SCORE_FORMULA", title="Consolidated Bid Score", description=CONSOLIDATED,
        formula_expression="CONSOLIDATED_SCORE=TECHNICAL_SCORE*TECHNICAL_WEIGHT+FINANCIAL_SCORE*FINANCIAL_WEIGHT",
        formula_variables=["CONSOLIDATED_SCORE","TECHNICAL_SCORE","FINANCIAL_SCORE"], formula_semantics="WEIGHTED_SUM",
        formula_multiplier=None, technical_weight_percent=70, financial_weight_percent=30)
    value.update(changes)
    return rule(handle, **value)


def test_weights_are_stored_separately():
    value=plan(CONSOLIDATED); item=CommercialFinancialBlueprintService(FakeProvider(payload(consolidated_rule(handle_for(value,"Consolidated"))))).execute(value).rules[0]
    assert (item.technical_weight_percent,item.financial_weight_percent)==(70,30)


def test_correct_consolidated_inputs_without_output_variable_do_not_review():
    value=plan(CONSOLIDATED); item=consolidated_rule(handle_for(value,"Consolidated"),formula_variables=["TECHNICAL_SCORE","FINANCIAL_SCORE"])
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert not result.requires_review


def test_weight_placeholders_are_representation_only_when_weights_are_grounded():
    value=plan(CONSOLIDATED); item=consolidated_rule(handle_for(value,"Consolidated"),formula_variables=["TECHNICAL_SCORE","FINANCIAL_SCORE","TECHNICAL_WEIGHT","FINANCIAL_WEIGHT"])
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert not result.requires_review and (result.technical_weight_percent,result.financial_weight_percent)==(70,30)


def test_weights_are_not_thresholds():
    value=plan(CONSOLIDATED); item=CommercialFinancialBlueprintService(FakeProvider(payload(consolidated_rule(handle_for(value,"Consolidated"))))).execute(value).rules[0]
    assert item.operator is None and item.percentage_value is None


def test_decimal_and_percent_weight_representations_are_equivalent():
    value=plan(CONSOLIDATED); item=consolidated_rule(handle_for(value,"Consolidated"), technical_weight_percent=.7, financial_weight_percent=.3)
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert (result.technical_weight_percent,result.financial_weight_percent)==(70,30) and not result.requires_review


def test_weight_mismatch_requires_review():
    value=plan(CONSOLIDATED); item=consolidated_rule(handle_for(value,"Consolidated"), technical_weight_percent=60, financial_weight_percent=40)
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.requires_review and (result.technical_weight_percent,result.financial_weight_percent)==(70,30)


def test_complete_weighted_combination_totals_one_hundred():
    value=plan(CONSOLIDATED); result=CommercialFinancialBlueprintService(FakeProvider(payload(consolidated_rule(handle_for(value,"Consolidated"))))).execute(value).rules[0]
    assert result.technical_weight_percent + result.financial_weight_percent == 100


def test_consolidated_and_financial_formulas_remain_distinct():
    value=plan(FINANCIAL,CONSOLIDATED); first=rule(handle_for(value,"Lowest")); second=consolidated_rule(handle_for(value,"Consolidated"))
    result=CommercialFinancialBlueprintService(FakeProvider(payload(first,second))).execute(value)
    assert result.accepted_count == 2 and {r.kind.value for r in result.rules} == {"FINANCIAL_SCORE_FORMULA","WEIGHTED_SCORE_FORMULA"}


def test_formula_not_deduplicated_with_percentage_rule():
    value=plan(CONSOLIDATED,"Performance security is 3% of contract value.")
    formula=consolidated_rule(handle_for(value,"Consolidated")); percentage=rule(handle_for(value,"3%"),kind="COMMERCIAL_RULE",title="Performance Security",description="Performance security is 3% of contract value.",formula_expression=None,formula_variables=[],formula_semantics=None,formula_multiplier=None,technical_weight_percent=None,financial_weight_percent=None,percentage_value=3)
    assert CommercialFinancialBlueprintService(FakeProvider(payload(formula,percentage))).execute(value).accepted_count == 2


@pytest.mark.parametrize(("text","expected"),[("Fee is INR 5 crore.","50000000"),("Fee is INR 25 lakh.","2500000"),("Fee is INR 40.","40")])
def test_grounded_money_normalization(text,expected):
    value=plan(text); item=rule(handle_for(value,"Fee"),kind="COMMERCIAL_RULE",title="Fee",description=text,formula_expression=None,formula_variables=[],formula_semantics=None,formula_multiplier=None,money_value=expected,currency="INR")
    assert CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0].money_value == expected


def test_currency_mismatch_requires_review_without_fx_conversion():
    text="Fee is INR 5 crore."; value=plan(text); item=rule(handle_for(value,"Fee"),kind="COMMERCIAL_RULE",title="Fee",description=text,formula_expression=None,formula_variables=[],formula_semantics=None,formula_multiplier=None,money_value="50000000",currency="USD")
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.currency == "INR" and result.requires_review


def test_unrelated_commercial_percentage_does_not_leak_into_weights():
    value=plan(CONSOLIDATED,"Liquidated damages are 2%."); item=consolidated_rule(handle_for(value,"Consolidated"))
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert (result.technical_weight_percent,result.financial_weight_percent)==(70,30)


def test_dates_and_reference_numbers_do_not_become_formula_values():
    text=FINANCIAL+" Reference 2022-IT-01 dated 25-10-2022."; value=plan(text)
    result=CommercialFinancialBlueprintService(FakeProvider(payload(rule(handle_for(value,"Lowest"))))).execute(value).rules[0]
    assert result.formula_multiplier == 100


def test_gemini_null_formula_fields_are_enriched_locally():
    value=plan(FINANCIAL); item=rule(handle_for(value,"Lowest"),formula_expression=None,formula_variables=[],formula_semantics=None,formula_multiplier=None)
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.formula_semantics.value == "RATIO_PERCENT" and result.formula_multiplier == 100


def test_formula_component_conflict_requires_review():
    value=plan(FINANCIAL); item=rule(handle_for(value,"Lowest"),formula_variables=["FINANCIAL_SCORE","BIDDER_BID_VALUE"],formula_multiplier=10)
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.requires_review and result.formula_multiplier == 100


def test_wrong_financial_operand_requires_review():
    value=plan(FINANCIAL); item=rule(handle_for(value,"Lowest"),formula_variables=["LOWEST_VALID_BID","TECHNICAL_SCORE"])
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.requires_review and "variables conflicted" in result.review_reason


def test_missing_required_financial_operand_requires_review():
    value=plan(FINANCIAL); item=rule(handle_for(value,"Lowest"),formula_variables=["BIDDER_BID_VALUE"])
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.requires_review and "variables conflicted" in result.review_reason


def test_missing_required_weighted_operand_requires_review():
    value=plan(CONSOLIDATED); item=consolidated_rule(handle_for(value,"Consolidated"),formula_variables=["TECHNICAL_SCORE"])
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.requires_review and "variables conflicted" in result.review_reason


def test_ambiguous_emd_amount_remains_review_required():
    text="EMD schedule contains INR 500000 and INR 10000 pending association."; value=plan(text,review_indexes={1})
    item=rule(handle_for(value,"EMD"),kind="COMMERCIAL_RULE",title="EMD",description=text,formula_expression=None,formula_variables=[],formula_semantics=None,formula_multiplier=None,money_value=None,currency=None)
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.requires_review and "local evidence" in result.review_reason.lower()


def test_ambiguous_formula_remains_unstructured():
    text="Financial score will be calculated according to the published method."; value=plan(text)
    item=rule(handle_for(value,"published"),kind="FINANCIAL_REQUIREMENT",title="Financial scoring",description=text,formula_expression=None,formula_variables=[],formula_semantics=None,formula_multiplier=None)
    result=CommercialFinancialBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]
    assert result.formula_expression is None and result.formula_multiplier is None


def test_safe_duplicate_rules_merge():
    value=plan(FINANCIAL); item=rule(handle_for(value,"Lowest")); result=CommercialFinancialBlueprintService(FakeProvider(payload(item,item))).execute(value)
    assert result.generated_count == 2 and result.accepted_count == 1


def test_different_formulas_do_not_merge():
    value=plan(FINANCIAL,CONSOLIDATED); result=CommercialFinancialBlueprintService(FakeProvider(payload(rule(handle_for(value,"Lowest")),consolidated_rule(handle_for(value,"Consolidated"))))).execute(value)
    assert result.accepted_count == 2


def test_usage_reports_one_request_zero_retries():
    value=plan(FINANCIAL); metadata={"provider_request_id":"r1","input_tokens":10,"output_tokens":5,"total_tokens":15}
    result=CommercialFinancialBlueprintService(FakeProvider(payload(rule(handle_for(value,"Lowest"))),metadata)).execute(value)
    assert (result.usage.request_count,result.usage.retry_count,result.usage.total_tokens)==(1,0,15)


def test_provider_failure_is_not_retried():
    provider=FakeProvider("",error=RuntimeError("offline"))
    with pytest.raises(CommercialFinancialSmokeTestError): CommercialFinancialBlueprintService(provider).execute(plan(FINANCIAL))
    assert provider.calls == 1


def test_local_review_state_propagates():
    value=plan(FINANCIAL,review_indexes={1}); result=CommercialFinancialBlueprintService(FakeProvider(payload(rule(handle_for(value,"Lowest"))))).execute(value).rules[0]
    assert result.requires_review and "local evidence" in result.review_reason.lower()


def test_strict_schema_rejects_unknown_fields():
    with pytest.raises(CommercialFinancialSmokeTestError): parse_commercial_financial_response('{"rules":[],"unexpected":true}')


def test_provider_uses_json_schema_no_tools_and_one_attempt():
    from google.genai import types
    value=plan(FINANCIAL); text=payload(rule(handle_for(value,"Lowest"))); client=type("Client",(),{})(); client.models=RecordingModels(text)
    GoogleCommercialFinancialProvider(None,"fake",client).generate("prompt"); config=client.models.calls[0]["config"]
    assert config.response_schema is None and config.response_json_schema == commercial_financial_response_json_schema()
    assert config.tools is None and config.automatic_function_calling.disable and config.http_options.retry_options.attempts == 1


def test_prompt_is_scoped_and_hides_internal_ids():
    value=plan(FINANCIAL); prompt=serialize_commercial_financial_request(select_commercial_financial_request(value))
    assert "SEMANTIC CATEGORY: COMMERCIAL_FINANCIAL" in prompt and "FIN-WU" not in prompt


def test_generation_config_uses_standard_json_schema():
    from google.genai import types
    config=build_commercial_financial_generation_config(types)
    assert config.response_json_schema and config.response_schema is None
