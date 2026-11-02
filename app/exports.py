"""Patient summary export helpers: PDF and HL7 FHIR R4 Bundle."""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from .db import DB, iso, utcnow

def patient_bundle(db: DB, p: dict, days: int = 30) -> dict:
    since = iso(utcnow().replace(microsecond=0) - __import__("datetime").timedelta(days=days))
    readings = db.all(
        "SELECT id, kind, value1, value2, context, source, taken_at FROM readings "
        "WHERE patient_id=? AND taken_at>=? ORDER BY taken_at", (p["id"], since))
    entries = [{
        "resource": {
            "resourceType": "Patient",
            "id": f"rafiq-patient-{p['id']}",
            "identifier": [{"system": "https://health-rafiq-1.onrender.com/patient-id", "value": str(p["id"])}],
            "name": [{"text": p["name"]}],
            "gender": {"m":"male","f":"female"}.get(p["gender"], "unknown"),
        }
    }]
    for r in readings:
        if r["kind"] == "glucose":
            code = {"coding":[{"system":"http://loinc.org","code":"2339-0","display":"Glucose [Mass/volume] in Blood"}]}
            comps = []
            value = r["value1"]
            unit = "mg/dL"
        else:
            code = {"coding":[{"system":"http://loinc.org","code":"85354-9","display":"Blood pressure panel"}]}
            comps = [
                {"code":{"coding":[{"system":"http://loinc.org","code":"8480-6","display":"Systolic blood pressure"}]},"valueQuantity":{"value":r["value1"],"unit":"mmHg"}},
                {"code":{"coding":[{"system":"http://loinc.org","code":"8462-4","display":"Diastolic blood pressure"}]},"valueQuantity":{"value":r["value2"],"unit":"mmHg"}},
            ]
            value = None; unit = None
        obs = {
            "resourceType":"Observation",
            "id":f"rafiq-reading-{r['id']}",
            "status":"final",
            "subject":{"reference":f"Patient/rafiq-patient-{p['id']}"},
            "effectiveDateTime":r["taken_at"]+"Z",
            "code":code,
        }
        if value is not None:
            obs["valueQuantity"]={"value":value,"unit":unit,"system":"http://unitsofmeasure.org","code":unit}
        if comps: obs["component"]=comps
        entries.append({"resource":obs})
    return {"resourceType":"Bundle","type":"collection","timestamp":datetime.now(timezone.utc).isoformat(),"entry":entries}

def pdf_bytes(db: DB, p: dict, days: int = 30) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from datetime import timedelta
    since = iso(utcnow() - timedelta(days=days))
    readings = db.all("SELECT kind,value1,value2,context,taken_at,level FROM readings WHERE patient_id=? AND taken_at>=? ORDER BY taken_at DESC", (p["id"], since))
    checkins = db.all("SELECT local_date,meds_taken,level,completed FROM checkins WHERE patient_id=? AND created_at>=? ORDER BY created_at DESC", (p["id"], since))
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=14*mm,leftMargin=14*mm,topMargin=14*mm,bottomMargin=14*mm)
    styles=getSampleStyleSheet()
    story=[Paragraph("Health Rafiq — Patient Summary",styles["Title"]),
           Paragraph(f"Patient: {p['name']} | Record ID: {p['id']}",styles["Normal"]),
           Paragraph(f"Period: last {days} days | Generated: {iso(utcnow())} UTC",styles["Normal"]), Spacer(1,8)]
    data=[["Date/time","Type","Value","Context","Level"]]
    for r in readings:
        val=f"{r['value1']:.0f}" if r["kind"]=="glucose" else f"{r['value1']:.0f}/{r['value2']:.0f}"
        data.append([r["taken_at"],r["kind"],val,r["context"] or "—",["Normal","Watch","Urgent"][min(2,int(r["level"]))]])
    story += [Paragraph("Vitals",styles["Heading2"]), Table(data,repeatRows=1,style=TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.grey),
        ("FONTSIZE",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP")]))]
    story += [Spacer(1,10),Paragraph("Daily check-ins",styles["Heading2"])]
    cdata=[["Date","Medication","Level","Completed"]]
    for c in checkins:
        cdata.append([c["local_date"],"Taken" if c["meds_taken"]==1 else "Missed" if c["meds_taken"]==0 else "Unknown",
                      ["Normal","Watch","Urgent"][min(2,int(c["level"]))],"Yes" if c["completed"] else "Partial"])
    story += [Table(cdata,repeatRows=1,style=TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),8)])),
              Spacer(1,8),Paragraph("This export is a clinical record summary, not a diagnosis or treatment recommendation.",styles["Italic"])]
    doc.build(story)
    return buf.getvalue()
