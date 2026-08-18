const defaultPrompts = {
  prompt1: "Rephrase: ",
  prompt2: "Correct: ",
  prompt3: "Translate: ",
  prompt4: "Give 3 equivalents for: ",
  prompt5: "",
  prompt6: "",
  prompt7: "",
  prompt8: "",
  prompt9: ""
};

document.addEventListener("DOMContentLoaded", () => {
  loadOptions();
  document.getElementById("save").addEventListener("click", saveOptions);
  document.getElementById("reset").addEventListener("click", resetDefaults);
});

function loadOptions() {
  const allKeys = [
    "prompt1",
    "prompt2",
    "prompt3",
    "prompt4",
    "prompt5",
    "prompt6",
    "prompt7",
    "prompt8",
    "prompt9"
  ];
  chrome.storage.local.get(allKeys, (result) => {
    allKeys.forEach((key) => {
      const field = document.getElementById(key);
      if (!field) return;

      if (result[key] === undefined) {
        field.value = defaultPrompts[key];
      } else {
        field.value = result[key];
      }
    });
  });
}

function saveOptions() {
  const newPrompts = {};
  for (let i = 1; i <= 9; i++) {
    const key = "prompt" + i;
    const field = document.getElementById(key);
    if (field) {
      newPrompts[key] = field.value.trim();
    }
  }
  chrome.storage.local.set(newPrompts, () => {
    alert("✅ Prompts saved.");
  });
}

function resetDefaults() {
  const resetPrompts = {};
  for (let i = 1; i <= 9; i++) {
    const key = "prompt" + i;
    resetPrompts[key] = defaultPrompts[key];
    const field = document.getElementById(key);
    if (field) {
      field.value = defaultPrompts[key];
    }
  }
  chrome.storage.local.set(resetPrompts, () => {
    alert("🔄 Prompts reset to defaults.");
  });
}