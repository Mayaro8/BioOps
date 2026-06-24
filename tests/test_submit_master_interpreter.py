from bioops.tools.submit_master_interpreter import SubmitMasterInterpreter
from bioops.tools.submit_master_parameter_matcher import SubmitMasterParameterMatcher


def test_numbered_step_requests_clarification():
    interpreter = SubmitMasterInterpreter(SubmitMasterParameterMatcher())

    result = interpreter.interpret(
        message="Run step2 for sample S123",
        provided_parameters={"sample_ids": "S123", "seq_type": "illumina"},
        candidate_step="step2",
    )

    assert result.status == "needs_clarification"
    assert "ambiguous" in result.explanation.lower()
    assert result.alternatives


def test_named_step_is_interpreted_to_known_stage():
    interpreter = SubmitMasterInterpreter(SubmitMasterParameterMatcher())

    result = interpreter.interpret(
        message="Run HLA parser for sample S123",
        provided_parameters={"sample_ids": "S123", "seq_type": "illumina"},
        candidate_step="hla_parser",
    )

    assert result.status == "interpreted"
    assert result.candidate_stage == "stage3"
    assert result.candidate_step == "hla_parser"
