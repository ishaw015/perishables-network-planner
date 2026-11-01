from agent.facts import fmt


def template_explanation(f: dict) -> dict:
    g = lambda k: f[k]["value"] if k in f else None
    used = ["line.store_id", "line.product_id", "store.status"]
    s = [f"Store {fmt(g('line.store_id'))}, product {fmt(g('line.product_id'))}: the plan status is {g('store.status')}."]
    if g("store.order_qty") is not None:
        used += ["store.order_qty", "store.target", "store.on_hand", "store.pending"]
        s.append(f"The policy orders {fmt(g('store.order_qty'))} units to reach a target of "
                 f"{fmt(g('store.target'))}, with {fmt(g('store.on_hand'))} on hand and "
                 f"{fmt(g('store.pending'))} already on the way.")
    if g("store.short_qty"):
        used += ["store.ship_qty", "store.short_qty"]
        s.append(f"The warehouse can ship {fmt(g('store.ship_qty'))} units, "
                 f"{fmt(g('store.short_qty'))} short.")
    if g("store.expiring_units"):
        used.append("store.expiring_units")
        s.append(f"About {fmt(g('store.expiring_units'))} units are expected to expire before they sell.")
    s.append("The quantity comes from the planning policy; the planner can approve, edit or reject it.")
    return {"answer": " ".join(s), "used_facts": used, "cannot_answer": False}