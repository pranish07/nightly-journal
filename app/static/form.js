(() => {
  "use strict";

  const goalList = document.getElementById("goal-list");
  const goalTemplate = document.getElementById("goal-row-template");
  const addGoal = document.getElementById("add-goal");
  const goalEmpty = document.getElementById("goal-empty");
  const planList = document.getElementById("plan-list");
  const planTemplate = document.getElementById("plan-row-template");
  const addPlan = document.getElementById("add-plan");
  const planEmpty = document.getElementById("plan-empty");
  const noGoals = document.getElementById("no_goals");
  const goalsFieldset = document.getElementById("goals-fieldset");
  const form = document.getElementById("entry-form");
  const maxRows = 10;

  const normalizeTitle = (value) =>
    value
      .normalize("NFKC")
      .trim()
      .replace(/\s+/g, " ")
      .toLowerCase()
      .replace(/[.!?;:,]+$/, "")
      .trim();

  const rows = (container) => Array.from(container.querySelectorAll("[data-row]"));

  const updateEmpty = (container, empty) => {
    empty.hidden = rows(container).length > 0;
  };

  const updateAddButton = (button, container) => {
    button.disabled = rows(container).length >= maxRows;
  };

  const bindIndex = (row, index) => {
    row.querySelectorAll("[name], [id], [for]").forEach((element) => {
      ["name", "id", "for"].forEach((attribute) => {
        if (element.hasAttribute(attribute)) {
          element.setAttribute(
            attribute,
            element.getAttribute(attribute).replaceAll("__INDEX__", String(index)),
          );
        }
      });
    });
    const number = row.querySelector("[data-row-number]");
    if (number) {
      number.textContent = String(index + 1);
    }
  };

  const reindex = (container) => {
    rows(container).forEach((row, index) => {
      row.querySelectorAll("[name], [id], [for]").forEach((element) => {
        ["name", "id", "for"].forEach((attribute) => {
          if (element.hasAttribute(attribute)) {
            element.setAttribute(
              attribute,
              element.getAttribute(attribute).replace(/_\d+$/, `_${index}`),
            );
          }
        });
      });
      const number = row.querySelector("[data-row-number]");
      if (number) {
        number.textContent = String(index + 1);
      }
    });
  };

  const addRow = (container, template, empty) => {
    if (rows(container).length >= maxRows) {
      return null;
    }
    const fragment = template.content.cloneNode(true);
    const row = fragment.firstElementChild;
    bindIndex(row, rows(container).length);
    container.append(fragment);
    updateEmpty(container, empty);
    return row;
  };

  const wireRemove = (container, empty, addButton) => {
    container.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-remove-row]");
      if (!remove) {
        return;
      }
      const row = remove.closest("[data-row]");
      if (row) {
        row.remove();
        reindex(container);
        updateEmpty(container, empty);
        updateAddButton(addButton, container);
      }
    });
  };

  if (goalList && goalTemplate && addGoal && goalEmpty) {
    addGoal.addEventListener("click", () => {
      const row = addRow(goalList, goalTemplate, goalEmpty);
      updateAddButton(addGoal, goalList);
      if (row) {
        const title = row.querySelector('input[name^="goal_title_"]');
        if (title) {
          title.focus();
        }
      }
    });
    wireRemove(goalList, goalEmpty, addGoal);
    updateEmpty(goalList, goalEmpty);
    updateAddButton(addGoal, goalList);
  }

  if (planList && planTemplate && addPlan && planEmpty) {
    addPlan.addEventListener("click", () => {
      const row = addRow(planList, planTemplate, planEmpty);
      updateAddButton(addPlan, planList);
      if (row) {
        const title = row.querySelector('input[name^="plan_title_"]');
        if (title) {
          title.focus();
        }
      }
    });
    wireRemove(planList, planEmpty, addPlan);
    updateEmpty(planList, planEmpty);
    updateAddButton(addPlan, planList);
  }

  if (noGoals && goalsFieldset) {
    const syncGoals = () => {
      goalsFieldset.disabled = noGoals.checked;
      goalsFieldset.hidden = noGoals.checked;
    };
    noGoals.addEventListener("change", syncGoals);
    syncGoals();
  }

  const reuse = document.getElementById("reuse-yesterday");
  if (reuse && goalList && goalTemplate && goalEmpty && addGoal) {
    reuse.addEventListener("click", () => {
      let titles = [];
      try {
        titles = JSON.parse(reuse.dataset.yesterdayGoals || "[]");
      } catch {
        titles = [];
      }
      const existing = new Set(
        rows(goalList)
          .map((row) => row.querySelector('input[name^="goal_title_"]'))
          .filter(Boolean)
          .map((input) => normalizeTitle(input.value))
          .filter(Boolean),
      );
      let added = 0;
      titles.forEach((item) => {
        if (rows(goalList).length >= maxRows) {
          return;
        }
        const title = typeof item === "string" ? item : item.title;
        const normalized =
          typeof item === "string" ? normalizeTitle(item) : item.normalized || normalizeTitle(item.title);
        if (!title || existing.has(normalized)) {
          return;
        }
        const row = addRow(goalList, goalTemplate, goalEmpty);
        if (!row) {
          return;
        }
        const input = row.querySelector('input[name^="goal_title_"]');
        if (input) {
          input.value = title;
        }
        existing.add(normalized);
        added += 1;
      });
      updateAddButton(addGoal, goalList);
      if (added > 0) {
        const first = goalList.querySelector('input[name^="goal_title_"]');
        if (first) {
          first.focus();
        }
      }
    });
  }

  if (form) {
    form.addEventListener("submit", () => {
      const submit = form.querySelector("[data-submit]");
      if (submit) {
        submit.disabled = true;
        submit.textContent = "Saving…";
      }
    });
  }
})();
