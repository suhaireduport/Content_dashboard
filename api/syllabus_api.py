"""HTTP client for the course content hierarchy (Subject -> Chapter -> Topic -> Subtopic).

Endpoints, as used by the app's own pages:
  GET /core/get/syllabus/children?syllabus=<parent id>&type=<level>   (JSON)
      -> {"children": [{"id", "title", "resource_type", "syllabus_type"}, ...]}
  GET /core/<level>/update/<id>                                      (HTML Edit form)
      -> the saved values, including the "availability" checkbox

The JSON endpoint has no availability field, so availability is read from the Edit form
(see availability_field).
"""

from playwright.sync_api import APIRequestContext, APIResponse

from api.course_api import EditFormParser
from config import BASE_URL


class SyllabusApi:
    CHILDREN_URL = f"{BASE_URL}/core/get/syllabus/children"
    # syllabus_type values returned by the children endpoint for each level
    SYLLABUS_TYPES = {"subject": 3, "chapter": 4, "topic": 5, "subtopic": 6}

    def __init__(self, request: APIRequestContext):
        self.request = request

    def get_children(self, parent_id: str, level: str) -> APIResponse:
        return self.request.get(self.CHILDREN_URL, params={"syllabus": str(parent_id), "type": level})

    def children(self, parent_id: str, level: str) -> list[dict]:
        return self.get_children(parent_id, level).json()["children"]

    def child_ids_and_titles(self, parent_id: str, level: str) -> dict[str, str]:
        """{id: title} with whitespace normalised the way the page displays titles."""
        return {
            str(child["id"]): " ".join(child["title"].split())
            for child in self.children(parent_id, level)
        }

    def get_list_page(self, level: str, parent_id: str) -> APIResponse:
        return self.request.get(f"{BASE_URL}/core/{level}/list/{parent_id}")

    def get_edit_form(self, level: str, item_id: str) -> APIResponse:
        return self.request.get(f"{BASE_URL}/core/{level}/update/{item_id}")

    def edit_form_values(self, level: str, item_id: str) -> dict:
        parser = EditFormParser()
        parser.feed(self.get_edit_form(level, item_id).text())
        return parser.values

    def availability_field(self, level: str, item_id: str) -> bool | None:
        """State of the Edit form's "Is Available" checkbox.

        Observed behaviour: the checkbox is only offered while the item is Not Available
        (returned unticked -> False). Once the item is Available the form no longer
        contains it, so this returns None.
        """
        return self.edit_form_values(level, item_id).get("availability")
