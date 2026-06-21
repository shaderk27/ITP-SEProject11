# backend/app/repositories/config_repository.py
from sqlalchemy.orm import Session
from app.models.config import LabGroup, Lab, LabAlias, RequesterLabMapping

class ConfigRepository:
    def __init__(self, db_session: Session):
        self.db = db_session

    def get_classification_maps(self):
        """Builds the dictionaries needed for the W7-04 Classifier."""
        
        # 1. Build WBS Map: { "WBS-CODE": "Lab Group Name" }
        wbs_map = {}
        groups = self.db.query(LabGroup).filter(LabGroup.wbs_code.isnot(None)).all()
        for group in groups:
            wbs_map[group.wbs_code] = group.lab_group_name

        # 2. Build Keyword Map: { "Alias Text": "Lab Name" }
        keyword_map = {}
        # Join aliases with labs to get the actual lab name
        aliases = self.db.query(LabAlias, Lab).join(Lab).all()
        for alias, lab in aliases:
            # We lowercase the alias text here to make matching case-insensitive later
            keyword_map[alias.alias_text.lower()] = lab.lab_name

        # 3. Build Requestor Map: { "Requestor Name": "Lab Name" }
        requestor_map = {}
        requestors = self.db.query(RequesterLabMapping, Lab).join(Lab, RequesterLabMapping.default_lab_id == Lab.lab_id).all()
        for req, lab in requestors:
            requestor_map[req.requester_name.lower()] = lab.lab_name

        return wbs_map, keyword_map, requestor_map