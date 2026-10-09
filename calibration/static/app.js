// Re-render device form when category changes so its custom fields appear.
document.addEventListener("change", function (e) {
  if (e.target.matches("select[data-reload]")) {
    const form = e.target.form;
    const flag = document.createElement("input");
    flag.type = "hidden";
    flag.name = "_reload";
    flag.value = "1";
    form.appendChild(flag);
    form.noValidate = true;
    form.submit();
  }
});
// Confirm buttons
document.addEventListener("click", function (e) {
  const el = e.target.closest("[data-confirm]");
  if (el && !confirm(el.dataset.confirm)) e.preventDefault();
});
// Copy-to-clipboard
document.addEventListener("click", function (e) {
  const el = e.target.closest("[data-copy]");
  if (!el) return;
  const input = document.getElementById(el.dataset.copy);
  navigator.clipboard.writeText(input.value).then(() => { el.textContent = "Copied"; });
});

// ---- Manufacturer / model dropdowns with "+" quick add (device form)
(function () {
  const brandSel = document.querySelector('select[data-lookup="manufacturer"]');
  const modelSel = document.querySelector('select[data-lookup="model"]');
  if (!brandSel || !modelSel) return;

  function filterModels() {
    const brand = brandSel.value;
    for (const opt of modelSel.options) {
      if (!opt.value) continue;
      const match = brand && opt.dataset.manufacturer === brand;
      opt.hidden = !match;
      opt.disabled = !match;
    }
    const cur = modelSel.selectedOptions[0];
    if (cur && cur.value && cur.disabled) modelSel.value = "";
  }
  // picking a model first fills in its brand
  modelSel.addEventListener("change", function () {
    const opt = modelSel.selectedOptions[0];
    if (opt && opt.dataset.manufacturer && !brandSel.value) { brandSel.value = opt.dataset.manufacturer; filterModels(); }
  });
  brandSel.addEventListener("change", filterModels);
  filterModels();

  const modalEl = document.getElementById("lookup-modal");
  const form = document.getElementById("lookup-form");
  const nameInput = document.getElementById("lookup-name");
  const errorEl = document.getElementById("lookup-error");
  const modal = new bootstrap.Modal(modalEl);
  let kind = null;

  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-lookup-add]");
    if (!btn) return;
    kind = btn.dataset.lookupAdd;
    errorEl.textContent = "";
    nameInput.value = "";
    const brandName = brandSel.value ? brandSel.selectedOptions[0].text : "";
    if (kind === "model" && !brandSel.value) {
      alert("Select or add the manufacturer first.");
      return;
    }
    document.getElementById("lookup-title").textContent = kind === "model" ? "Add model" : "Add manufacturer";
    document.getElementById("lookup-context").textContent = kind === "model" ? "Manufacturer: " + brandName : "";
    modal.show();
  });
  modalEl.addEventListener("shown.bs.modal", () => nameInput.focus());

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const data = new FormData();
    data.append("name", nameInput.value);
    if (kind === "model") data.append("manufacturer", brandSel.value);
    const csrf = document.querySelector("input[name=csrfmiddlewaretoken]").value;
    let res, body;
    try {
      res = await fetch(kind === "model" ? form.dataset.modelUrl : form.dataset.manufacturerUrl, {
        method: "POST", body: data, headers: { "X-CSRFToken": csrf }, credentials: "same-origin",
      });
      body = await res.json();
    } catch (err) {
      errorEl.textContent = "Could not save (connection problem or session expired).";
      return;
    }
    if (!res.ok) { errorEl.textContent = body.error || "Could not save."; return; }
    const sel = kind === "model" ? modelSel : brandSel;
    let opt = [...sel.options].find(o => o.value === String(body.id));
    if (!opt) {
      opt = new Option(body.name, body.id);
      if (kind === "model") opt.dataset.manufacturer = String(body.manufacturer);
      // keep alphabetical order
      const before = [...sel.options].find(o => o.value && o.text.localeCompare(body.name) > 0);
      sel.add(opt, before || null);
    }
    sel.value = String(body.id);
    if (kind === "manufacturer") filterModels();
    modal.hide();
  });
})();
