import hashlib
import json

import pytest

from app.models.blueprint import NormalizedRequirement, RequirementCategory, SourceReference
from app.models.blueprint_evidence import SemanticRequestCategory
from app.models.document_intelligence import CandidateEvidence, CandidateType, LocalCandidate, ResolutionCapability
from app.models.extraction import ExtractedDocument, ExtractedPage, ExtractionAssessment, PdfMetadata
from app.models.hybrid_blueprint import GeminiWorkUnit, GroundedContext, WorkUnitReason
from app.services.contractual_other_blueprint import (
    ContractualOtherBlueprintService, ContractualOtherSmokeTestError, GoogleContractualOtherProvider,
    build_contractual_other_generation_config, contractual_other_response_json_schema,
    parse_contractual_other_response, select_contractual_other_requests, serialize_contractual_other_request,
)
from app.services.document_intelligence import LocalDocumentIntelligenceService
from app.services.evidence_packager import BlueprintEvidencePackager
from app.services.hybrid_blueprint import build_local_draft


def document(*texts):
    pages=[ExtractedPage(page_number=i,text=t,character_count=len(t),word_count=len(t.split())) for i,t in enumerate(texts,1)]
    raw="".join(texts).encode()
    return ExtractedDocument(filename="contract.pdf",sha256=hashlib.sha256(raw).hexdigest(),page_count=len(pages),
        total_characters=sum(map(len,texts)),total_words=sum(len(t.split()) for t in texts),text_pages=len(pages),empty_pages=0,
        assessment=ExtractionAssessment.TEXT_EXTRACTABLE,metadata=PdfMetadata(),pages=pages)


def plan(*texts, review_indexes=None, max_request=80_000):
    review_indexes=review_indexes or set(); source=document(*texts); draft=build_local_draft(LocalDocumentIntelligenceService().analyze(source)); units=[]
    for i,text in enumerate(texts,1):
        section=f"CON-SECTION-{i}"
        candidate=LocalCandidate(candidate_id=f"CON-LOCAL-{i}",candidate_type=CandidateType.SEMANTIC,category=RequirementCategory.CONTRACTUAL,
            raw_text=text,normalized=NormalizedRequirement(),evidence=[CandidateEvidence(source_reference=SourceReference(page_number=i,section="CONTRACT",excerpt=text[:600]),section_id=section)],
            confidence=.6,ambiguous=i in review_indexes,ambiguity_reason="Needs legal review" if i in review_indexes else None,
            resolution_capability=ResolutionCapability.REVIEW_REQUIRED if i in review_indexes else ResolutionCapability.LLM_REQUIRED)
        units.append(GeminiWorkUnit(work_unit_id=f"CON-WU-{i}",prompt_version="hybrid-v2",document_sha256=source.sha256,
            reason=WorkUnitReason.UNRESOLVED_CANDIDATES,section_ids=[section],page_numbers=[i],
            context=[GroundedContext(page_number=i,section_id=section,heading="CONTRACT",text=text)],candidates=[candidate]))
    return BlueprintEvidencePackager(max_request_characters=max_request).package(draft,units,source.total_characters)


def handle_for(value, phrase):
    return next(record.handle for request in select_contractual_other_requests(value) for record in request.records if phrase.casefold() in record.text.casefold())


def rule(handle, description="The Bidder shall deliver the system within 15 days.", **changes):
    value={"kind":"DELIVERY_REQUIREMENT","title":"System delivery","description":description,"responsible_party":"BIDDER",
        "beneficiary_or_counterparty":"PURCHASER","obligation_semantics":"MUST","action_or_obligation":"Deliver the system",
        "condition":None,"operator":None,"numeric_value":None,"percentage_value":None,"money_value":None,"currency":None,
        "duration_value":15,"duration_unit":"DAY","deadline_or_timing":None,"consequence_or_remedy":None,"mandatory":True,
        "expected_evidence":[],"evidence_ids":[handle],"requires_review":False,"review_reason":None}
    value.update(changes); return value


def payload(*rules): return json.dumps({"rules":list(rules)})


class FakeProvider:
    model="fake-gemini"
    def __init__(self,responses,metadata=None,error=None):
        self.responses=list(responses) if isinstance(responses,(list,tuple)) else [responses]; self.metadata=metadata or {}; self.error=error; self.calls=0; self.prompts=[]
    def generate(self,prompt):
        self.prompts.append(prompt); index=self.calls; self.calls+=1
        if self.error: raise self.error
        return self.responses[min(index,len(self.responses)-1)],self.metadata


class RecordingModels:
    def __init__(self,text): self.text=text; self.calls=[]
    def generate_content(self,**kwargs): self.calls.append(kwargs); return type("Response",(),{"text":self.text,"response_id":"r","usage_metadata":None})()


def execute(value,item): return ContractualOtherBlueprintService(FakeProvider(payload(item))).execute(value).rules[0]


def test_only_contractual_other_requests_execute():
    value=plan("The Bidder shall deliver the system within 15 days.")
    assert select_contractual_other_requests(value)[0].category==SemanticRequestCategory.CONTRACTUAL_OTHER


@pytest.mark.parametrize("category",[SemanticRequestCategory.QUALIFICATION,SemanticRequestCategory.TECHNICAL,SemanticRequestCategory.COMMERCIAL_FINANCIAL])
def test_other_categories_cannot_execute(category):
    value=plan("The Bidder shall deliver the system within 15 days."); value.semantic_requests[0]=value.semantic_requests[0].model_copy(update={"category":category})
    provider=FakeProvider(payload())
    with pytest.raises(ContractualOtherSmokeTestError): ContractualOtherBlueprintService(provider).execute(value)
    assert provider.calls==0


def test_unsupported_handle_is_rejected():
    result=ContractualOtherBlueprintService(FakeProvider(payload(rule("E9999")))).execute(plan("The Bidder shall deliver the system within 15 days."))
    assert result.accepted_count==0 and result.unsupported_evidence_handle_count==1


def test_full_provenance_restoration():
    value=plan("The Bidder shall deliver the system within 15 days."); result=execute(value,rule(handle_for(value,"deliver")))
    assert result.source_pages==[1] and result.source_section_ids==["CON-SECTION-1"] and result.source_work_unit_ids==["CON-WU-1"] and result.candidate_ids==["CON-LOCAL-1"]


def test_stable_ids_are_deterministic():
    value=plan("The Bidder shall deliver the system within 15 days."); item=rule(handle_for(value,"deliver"))
    assert execute(value,item).rule_id==execute(value,item).rule_id


def test_mandatory_obligation_representation():
    value=plan("The Bidder shall deliver the system within 15 days."); result=execute(value,rule(handle_for(value,"deliver")))
    assert result.obligation_semantics.value=="MUST" and result.mandatory


def test_prohibition_representation():
    text="The Bidder shall not subcontract the services."; value=plan(text); item=rule(handle_for(value,"subcontract"),description=text,obligation_semantics="MUST_NOT",duration_value=None,duration_unit=None)
    assert execute(value,item).obligation_semantics.value=="MUST_NOT"


def test_purchaser_right_is_not_vendor_obligation():
    text="IIITB may terminate the Contract for material breach."; value=plan(text); item=rule(handle_for(value,"terminate"),description=text,responsible_party="CLIENT",obligation_semantics="RIGHT",duration_value=None,duration_unit=None)
    result=execute(value,item); assert result.responsible_party.value=="CLIENT" and result.obligation_semantics.value=="RIGHT"


@pytest.mark.parametrize(("text","party"),[("The selected bidder shall honor the contractual obligations.","SELECTED_BIDDER"),("The service provider must maintain contractual records.","SERVICE_PROVIDER"),("The vendor should honor contractual duties.","VENDOR")])
def test_responsible_party_preserved(text,party):
    value=plan(text); item=rule(handle_for(value,text.split()[1]),description=text,responsible_party=party,duration_value=None,duration_unit=None,obligation_semantics="MUST" if "must" in text else "SHOULD" if "should" in text else "MUST")
    assert execute(value,item).responsible_party.value==party


def test_unknown_party_remains_nullable_and_reviewable():
    text="Support arrangements are subject to further clarification."; value=plan(text,review_indexes={1}); item=rule(handle_for(value,"Support"),description=text,responsible_party=None,obligation_semantics=None,duration_value=None,duration_unit=None,requires_review=True,review_reason="Actor unclear")
    result=execute(value,item); assert result.responsible_party is None and result.requires_review


def test_relative_duration_normalization():
    value=plan("The Bidder shall deliver the system within 15 days."); result=execute(value,rule(handle_for(value,"deliver"),duration_value=None,duration_unit=None))
    assert (result.duration_value,result.duration_unit.value)==(15,"DAY") and result.deadline_or_timing is None


def test_absolute_date_is_distinct_from_duration():
    text="The Bidder shall complete the contractual obligations on or before 31 March 2027."; value=plan(text); item=rule(handle_for(value,"complete"),description=text,duration_value=None,duration_unit=None,deadline_or_timing=None)
    result=execute(value,item); assert result.deadline_or_timing.endswith("31 March 2027") and result.duration_value is None


@pytest.mark.parametrize(("text","expected"),[("The Bidder shall pay INR 5 crore as damages.","50000000"),("The Bidder shall pay INR 25 lakh as damages.","2500000"),("The Bidder shall pay INR 4000 as damages.","4000")])
def test_money_normalization(text,expected):
    value=plan(text); item=rule(handle_for(value,"pay"),description=text,money_value=None,currency=None,duration_value=None,duration_unit=None)
    result=execute(value,item); assert result.money_value==expected and result.currency=="INR"


def test_percentage_normalization_and_association():
    text="Liquidated damages shall not exceed 3% of contract value."; value=plan(text); item=rule(handle_for(value,"damages"),description=text,responsible_party=None,percentage_value=None,duration_value=None,duration_unit=None)
    assert execute(value,item).percentage_value==3


def test_unrelated_percentage_does_not_leak_between_rules():
    value=plan("Service availability shall be 99%.","Liquidated damages shall be 3% of contract value.")
    item=rule(handle_for(value,"availability"),description="Service availability shall be 99%.",responsible_party=None,percentage_value=None,duration_value=None,duration_unit=None)
    assert execute(value,item).percentage_value==99


def test_reference_number_is_not_measurable_value():
    text="Contract reference 2024-15 applies to the services."; value=plan(text); item=rule(handle_for(value,"reference"),description=text,responsible_party=None,obligation_semantics=None,duration_value=None,duration_unit=None,numeric_value=None)
    result=execute(value,item); assert result.numeric_value is None and result.duration_value is None and result.percentage_value is None


def test_gemini_null_reliable_values_are_enriched():
    value=plan("The Bidder shall deliver within 10 days with damages capped at 2%."); item=rule(handle_for(value,"deliver"),description="The Bidder shall deliver within 10 days with damages capped at 2%.",duration_value=None,duration_unit=None,percentage_value=None)
    result=execute(value,item); assert result.duration_value==10 and result.percentage_value==2


def test_numeric_conflict_uses_local_and_requires_review():
    value=plan("The Bidder shall deliver within 10 days."); item=rule(handle_for(value,"deliver"),description="The Bidder shall deliver within 10 days.",duration_value=20,duration_unit="DAY")
    result=execute(value,item); assert result.duration_value==10 and result.requires_review


def test_actor_conflict_uses_local_and_requires_review():
    text="The Bidder shall perform the contractual obligations."; value=plan(text); item=rule(handle_for(value,"perform"),description=text,responsible_party="PURCHASER",duration_value=None,duration_unit=None)
    result=execute(value,item); assert result.responsible_party.value=="BIDDER" and result.requires_review


def test_ambiguous_legal_clause_remains_review():
    text="Liability allocation is subject to the final agreement."; value=plan(text,review_indexes={1}); item=rule(handle_for(value,"Liability"),description=text,responsible_party=None,obligation_semantics=None,duration_value=None,duration_unit=None,requires_review=True,review_reason="Incomplete legal clause")
    assert execute(value,item).requires_review


def test_similar_durations_do_not_deduplicate():
    value=plan("The Bidder shall respond within 2 days.","The Bidder shall respond within 5 days.")
    items=[rule(handle_for(value,"2 days"),description="The Bidder shall respond within 2 days.",duration_value=2),rule(handle_for(value,"5 days"),description="The Bidder shall respond within 5 days.",duration_value=5)]
    assert ContractualOtherBlueprintService(FakeProvider(payload(*items))).execute(value).accepted_count==2


def test_similar_consequences_do_not_deduplicate():
    text="The Bidder shall remedy a service breach."; value=plan(text); handle=handle_for(value,"remedy")
    one=rule(handle,description=text,duration_value=None,duration_unit=None,consequence_or_remedy="Service credit")
    two=rule(handle,description=text,duration_value=None,duration_unit=None,consequence_or_remedy="Termination")
    assert ContractualOtherBlueprintService(FakeProvider(payload(one,two))).execute(value).accepted_count==2


def test_safe_exact_duplicate_merges_provenance():
    text="The Bidder shall deliver within 15 days."; value=plan(text); item=rule(handle_for(value,"deliver"),description=text)
    result=ContractualOtherBlueprintService(FakeProvider(payload(item,item))).execute(value); assert result.generated_count==2 and result.accepted_count==1


def test_local_review_state_propagates():
    text="The Bidder shall comply with the unresolved clause."; value=plan(text,review_indexes={1}); item=rule(handle_for(value,"comply"),description=text,duration_value=None,duration_unit=None)
    assert execute(value,item).requires_review


def test_usage_metrics_for_one_request():
    value=plan("The Bidder shall deliver within 15 days."); metadata={"input_tokens":10,"output_tokens":5,"total_tokens":15}
    result=ContractualOtherBlueprintService(FakeProvider(payload(rule(handle_for(value,"deliver"),description="The Bidder shall deliver within 15 days.")),metadata)).execute(value)
    assert (result.usage.request_count,result.usage.retry_count,result.usage.total_tokens)==(1,0,15)


def test_safety_split_preserves_all_evidence_without_truncation():
    texts=tuple(f"The Bidder shall perform contractual obligation {i} within {i+1} days under the binding agreement." for i in range(1,7))
    value=plan(*texts,max_request=260); requests=select_contractual_other_requests(value)
    evidence_ids={item.evidence_id for package in value.packages for item in package.evidence_items if item.categories==[RequirementCategory.CONTRACTUAL]}
    routed_ids={record.evidence_id for request in requests for record in request.records}
    assert len(requests)>1 and evidence_ids==routed_ids and all(request.character_count<=260 or len(request.records)==1 for request in requests)


def test_multi_request_usage_counts_actual_calls_and_tokens():
    value=plan("The Bidder shall perform contractual obligation one within 2 days under the agreement.","The Bidder shall perform contractual obligation two within 3 days under the agreement.",max_request=180)
    requests=select_contractual_other_requests(value); provider=FakeProvider([payload() for _ in requests],{"input_tokens":2,"output_tokens":1,"total_tokens":3})
    result=ContractualOtherBlueprintService(provider).execute(value)
    assert result.usage.request_count==len(requests)==provider.calls and result.usage.total_tokens==3*len(requests)


def test_strict_schema_rejects_unknown_fields():
    with pytest.raises(ContractualOtherSmokeTestError): parse_contractual_other_response('{"rules":[],"unexpected":true}')


def test_provider_uses_json_schema_and_one_attempt():
    from google.genai import types
    client=type("Client",(),{})(); client.models=RecordingModels(payload())
    GoogleContractualOtherProvider(None,"fake",client).generate("prompt"); config=client.models.calls[0]["config"]
    assert config.response_schema is None and config.response_json_schema==contractual_other_response_json_schema() and config.tools is None and config.automatic_function_calling.disable and config.http_options.retry_options.attempts==1


def test_prompt_is_scoped_and_hides_internal_ids():
    value=plan("The Bidder shall deliver within 15 days."); prompt=serialize_contractual_other_request(select_contractual_other_requests(value)[0])
    assert "SEMANTIC CATEGORY: CONTRACTUAL_OTHER" in prompt and "CON-WU" not in prompt


def test_provider_failure_is_not_retried():
    provider=FakeProvider("",error=RuntimeError("offline"))
    with pytest.raises(ContractualOtherSmokeTestError): ContractualOtherBlueprintService(provider).execute(plan("The Bidder shall deliver within 15 days."))
    assert provider.calls==1


def test_absolute_date_and_relative_duration_can_coexist_without_conversion():
    text="The Bidder shall respond within 5 days and complete work on or before 31 March 2027."; value=plan(text); item=rule(handle_for(value,"respond"),description=text,duration_value=None,duration_unit=None,deadline_or_timing=None)
    result=execute(value,item); assert result.duration_value==5 and result.deadline_or_timing.endswith("31 March 2027")


@pytest.mark.parametrize(("text","party","semantics"),[
    ("The Purchaser may terminate the agreement for default.","PURCHASER","RIGHT"),
    ("The Vendor may appeal the decision within 3 days.","VENDOR","RIGHT"),
    ("The Bidder should indemnify the purchaser against direct loss.","BIDDER","SHOULD"),
    ("The Bidder shall perform the contractual obligations.","BIDDER","MUST"),
    ("The Bidder shall not assign the agreement.","BIDDER","MUST_NOT"),
    ("The Bidder must preserve contractual records.","BIDDER","MUST"),
    ("The Bidder shall be entitled to seek a remedy.","BIDDER","RIGHT"),
    ("Either party may refer the dispute to arbitration.","BOTH_PARTIES","RIGHT"),
])
def test_explicit_modal_and_actor_replay_shapes(text,party,semantics):
    value=plan(text); item=rule(handle_for(value,text.split()[1]),description=text,responsible_party=party,
        obligation_semantics=semantics,duration_value=3 if "3 days" in text else None,duration_unit="DAY" if "3 days" in text else None)
    result=execute(value,item)
    assert result.responsible_party.value==party and result.obligation_semantics.value==semantics and not result.requires_review


def test_may_remains_permission_when_condition_and_deadline_exist():
    text="If the decision is adverse, the Vendor may appeal within 3 days."; value=plan(text)
    item=rule(handle_for(value,"appeal"),description=text,responsible_party="VENDOR",obligation_semantics="RIGHT",
        condition="If the decision is adverse",duration_value=3,duration_unit="DAY")
    result=execute(value,item)
    assert result.obligation_semantics.value=="RIGHT" and result.condition=="If the decision is adverse" and not result.requires_review


def test_expected_passive_contract_clause_does_not_create_actor_or_must():
    text="The initial contract is expected to be signed for 3 years with yearly renewals."; value=plan(text)
    item=rule(handle_for(value,"expected"),description=text,responsible_party=None,obligation_semantics=None,duration_value=3,duration_unit="YEAR")
    result=execute(value,item)
    assert result.responsible_party is None and result.obligation_semantics is None and not result.requires_review


def test_explicit_client_acronym_actor_is_authoritative():
    text="ABCX may terminate the agreement for material default."; value=plan(text)
    item=rule(handle_for(value,"terminate"),description=text,responsible_party="CLIENT",obligation_semantics="RIGHT",duration_value=None,duration_unit=None)
    result=execute(value,item); assert result.responsible_party.value=="CLIENT" and result.obligation_semantics.value=="RIGHT"


def test_genuine_semantics_conflict_still_reviews():
    text="The Vendor may appeal the decision."; value=plan(text)
    item=rule(handle_for(value,"appeal"),description=text,responsible_party="VENDOR",obligation_semantics="MUST",duration_value=None,duration_unit=None)
    result=execute(value,item); assert result.obligation_semantics.value=="RIGHT" and result.requires_review


def test_multi_stage_dispute_modalities_remain_reviewable():
    text="Both parties shall attempt amicable resolution. Either party may refer the dispute to arbitration."
    value=plan(text); item=rule(handle_for(value,"resolution"),description=text,responsible_party=None,obligation_semantics=None,
        duration_value=None,duration_unit=None,requires_review=True,review_reason="Multiple dispute stages")
    result=execute(value,item); assert result.requires_review
