from scripts.evaluate import evaluate


def test_apple_reference_and_synthetic_benchmark():
    result=evaluate()
    assert result["count"]>=10
    assert result["passed"]==result["count"],result
