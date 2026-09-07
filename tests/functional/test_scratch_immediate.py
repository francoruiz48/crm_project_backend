from app.models.team import Team

def test_scratch_bulk_assign_immediate_response_has_updater(api, db_session, initial_structure):
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    api.create_lead_field(campaign_id=camp_id, name="Campo Libre", field_type_code="STRING", required=False)
    team_a = Team(name="Equipo Scratch", organization_id=org_id)
    db_session.add(team_a)
    db_session.commit()

    lead = api.create_lead(campaign_id=camp_id, values=[])

    result = api.bulk_assign(lead_ids=[lead["id"]], target_team_id=team_a.public_uuid)
    print("IMMEDIATE RESPONSE:", result)
    assert result[0].get("updater") is not None, "BUG: la respuesta inmediata del PATCH no trae updater"
