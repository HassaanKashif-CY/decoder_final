import json
from typing import Any

from openai import OpenAI

from backend.core.config import get_settings


class OpenAIClient:

    def __init__(self):

        settings = get_settings()

        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured."
            )

        self.client = OpenAI(
            api_key=settings.openai_api_key
        )

        self.model = (
            settings.openai_model
        )

    def generate_json(
        self,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:

        try:

            response = (
                self.client.responses.create(
                    model=self.model,
                    instructions=instructions,
                    input=input_text,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": schema_name,
                            "strict": True,
                            "schema": schema,
                        }
                    },
                )
            )

            return self._parse_response(
                response
            )

        except Exception as schema_error:

            print(
                "OpenAI JSON schema mode failed:"
            )
            print(schema_error)
            print(
                "Retrying with JSON object mode..."
            )

            try:

                response = (
                    self.client.responses.create(
                        model=self.model,
                        instructions=(
                            instructions
                            + "\n\n"
                            "RETURN ONLY VALID JSON."
                        ),
                        input=input_text,
                        text={
                            "format": {
                                "type": "json_object"
                            }
                        },
                    )
                )

                return self._parse_response(
                    response
                )

            except Exception as json_error:

                raise RuntimeError(
                    "OpenAI structured JSON request "
                    "failed. "
                    f"Schema error: {schema_error}. "
                    f"JSON mode error: {json_error}."
                ) from json_error

    def generate_pdf_json(
        self,
        pdf_path: str,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:

        uploaded_file = None

        try:

            with open(
                pdf_path,
                "rb",
            ) as pdf_file:

                uploaded_file = (
                    self.client.files.create(
                        file=pdf_file,
                        purpose="user_data",
                    )
                )

            response = (
                self.client.responses.create(
                    model=self.model,
                    instructions=instructions,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_file",
                                    "file_id": (
                                        uploaded_file.id
                                    ),
                                },
                                {
                                    "type": "input_text",
                                    "text": input_text,
                                },
                            ],
                        }
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": schema_name,
                            "strict": True,
                            "schema": schema,
                        }
                    },
                )
            )

            return self._parse_response(
                response
            )

        finally:

            if uploaded_file is not None:

                try:
                    self.client.files.delete(
                        uploaded_file.id
                    )
                except Exception as exc:
                    print(
                        "Could not delete uploaded "
                        f"OpenAI file: {exc}"
                    )

    def _parse_response(
        self,
        response: Any,
    ) -> dict[str, Any]:

        output_text = getattr(
            response,
            "output_text",
            None,
        )

        if not output_text:
            raise RuntimeError(
                "OpenAI returned an empty response."
            )

        try:

            parsed = json.loads(
                output_text
            )

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "OpenAI returned invalid JSON: "
                f"{exc}"
            ) from exc

        if not isinstance(
            parsed,
            dict,
        ):
            raise RuntimeError(
                "OpenAI JSON response must "
                "be an object."
            )

        return parsed