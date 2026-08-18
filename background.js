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

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(Object.keys(defaultPrompts), (stored) => {
    const toSet = {};
    for (const key in defaultPrompts) {
      if (!stored[key]) {
        toSet[key] = defaultPrompts[key];
      }
    }
    if (Object.keys(toSet).length > 0) {
      chrome.storage.local.set(toSet);
    }
  });
});

chrome.commands.onCommand.addListener((command) => {
  chrome.storage.local.get(command, (result) => {
    const promptText = result[command] ?? defaultPrompts[command];
    if (!promptText) return;

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length === 0) return;
      const tab = tabs[0];

      chrome.tabs.sendMessage(tab.id, {
        action: "insertPrompt",
        text: promptText
      }, () => {
        if (chrome.runtime.lastError) {
          console.warn("Unable to inject prompt:", chrome.runtime.lastError);
        }
      });
    });
  });
});
