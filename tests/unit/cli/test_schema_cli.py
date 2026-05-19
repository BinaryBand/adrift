import json

from typer.testing import CliRunner

from adrift.cli.root import app


def test_schema_compile_writes_json_schema(tmp_path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "podcasts.schema.json"

    result = runner.invoke(
        app,
        ["schema", "compile", "--output", str(output_path)],
        color=False,
    )

    assert result.exit_code == 0
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert payload["type"] == "object"
    assert "podcasts" in payload.get("properties", {})
