382
        results.append(comp)
383    return {"results": results}
384​
385@app.get("/api/interaction")
386def interaction(a: str, b: str):
387    """Get interaction details between two compounds by id or name."""
388    a_id = resolve_compound(a)
389    b_id = resolve_compound(b)
390    if not a_id or not b_id:
391        raise HTTPException(status_code=404, detail="One or both compounds not found")
392    for inter in INTERACTIONS:
393        if (inter["a"] == a_id and inter["b"] == b_id) or (inter["bidirectional"] and inter["a"] == b_id and inter["b"] == a_id):
394            risk_score = compute_risk(inter)
395            sources_detail = [SOURCES[sid] for sid in inter["sources"] if sid in SOURCES]
396            return {"interaction": inter, "risk_score": risk_score, "sources": sources_detail}
397    raise HTTPException(status_code=404, detail="No known interaction")
398​
399class StackRequest(BaseModel):
400    compounds: List[str]
401​
402@app.post("/api/stack/check")
403def check_stack(payload: StackRequest):
404    """Check interactions within a stack of compounds."""
405    ids: List[str] = []
406    for ident in payload.compounds:
407        cid = resolve_compound(ident)
408        if not cid:
409            raise HTTPException(status_code=404, detail=f"Compound not found: {ident}")
410        ids.append(cid)
411    interactions_out: List[dict] = []
412    for i in range(len(ids)):
413        for j in range(i+1, len(ids)):
414            a_id = ids[i]
415            b_id = ids[j]
416            for inter in INTERACTIONS:
417                if (inter["a"] == a_id and inter["b"] == b_id) or (inter["bidirectional"] and inter["a"] == b_id and inter["b"] == a_id):
418                    interactions_out.append({
419                        "a": a_id,
420                        "b": b_id,
421                        "severity": inter["severity"],
422                        "evidence": inter["evidence"],
423                        "effect": inter["effect"],
424                        "action": inter["action"],
425                        "risk_score": compute_risk(inter),
426                    })
427    return {"interactions": interactions_out}