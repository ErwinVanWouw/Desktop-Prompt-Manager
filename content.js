chrome.runtime.onMessage.addListener((request) => {
  if (request.action !== "insertPrompt") return;
  const prompt = request.text;

  const editable = findChatInput();
  if (editable) {
    editable.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, prompt);
    placeCaretAtEnd(editable);
    return;
  }

  const inputBox = document.querySelector("textarea, input[type='text']");
  if (inputBox) {
    inputBox.focus();
    inputBox.value = prompt;
    inputBox.dispatchEvent(new Event('input', { bubbles: true }));
    return;
  }

  console.warn("Prompt Manager: No suitable input field found.");
});

function findChatInput() {
  const all = [...document.querySelectorAll("div[contenteditable='true']")];
  return all.find(el => {
    const rect = el.getBoundingClientRect();
    return rect.width > 100 && rect.height > 20 && rect.bottom > 0;
  }) || all[0] || null;
}

function placeCaretAtEnd(el) {
  el.focus();
  if (window.getSelection && document.createRange) {
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }
}