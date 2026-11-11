// The overview put in another order while it is arranged: a card dragged
// with a mouse anywhere on it or a finger on its grip, or moved a place at a
// time by its grip's arrow keys. The cards make room by their order rather
// than by moving in the page, so no frame loads again, and each new order
// goes to the server.
const arranged = (board) => {
  // as they show, which after a move is not as they stand in the page
  const slots = [...board.querySelectorAll(":scope > .slot:not(.hole)")].sort(
    (one, other) => (one.style.order || 0) - (other.style.order || 0),
  );
  slots.forEach((one, place) => (one.style.order = place));
  return slots;
};
const keys = (slots) => slots.map((one) => one.dataset.key).join(",");
const save = (board, slots) => {
  const form = board.querySelector("form");
  form.elements.order.value = keys(slots);
  form.requestSubmit();
};

document.addEventListener("keydown", (event) => {
  const grip = event.target.closest?.(".arranging .slot .grip");
  const step = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[event.key];
  if (!grip || !step) return;
  event.preventDefault();
  const board = grip.closest(".board");
  const slots = arranged(board);
  const place = slots.indexOf(grip.closest(".slot"));
  if (place + step < 0 || place + step >= slots.length) return;
  slots.splice(place + step, 0, ...slots.splice(place, 1));
  slots.forEach((one, at) => (one.style.order = at));
  save(board, slots);
});

document.addEventListener("pointerdown", (event) => {
  if (!document.body.classList.contains("arranging") || event.button !== 0) return;
  const slot = event.target.closest(".slot:not(.hole)");
  if (!slot || (event.pointerType !== "mouse" && !event.target.closest(".grip"))) return;
  event.preventDefault();
  const board = slot.parentElement;
  const slots = arranged(board);
  const byOrder = (one, other) => one.style.order - other.style.order;
  const was = keys(slots);
  const box = slot.getBoundingClientRect();
  const hole = document.createElement("div");
  hole.className = `${slot.className} hole`;
  hole.style.height = `${box.height}px`;
  hole.style.order = slot.style.order;
  board.append(hole);
  const offset = { x: event.clientX - box.left, y: event.clientY - box.top };
  Object.assign(slot.style, { width: `${box.width}px`, left: `${box.left}px`, top: `${box.top}px` });
  slot.classList.add("lifted");
  // the card keeps the pointer let go anywhere, out of the frame too: it
  // never moves in the page, which would let go of it
  slot.setPointerCapture(event.pointerId);
  const move = (moved) => {
    slot.style.left = `${moved.clientX - offset.x}px`;
    slot.style.top = `${moved.clientY - offset.y}px`;
    // near an edge the page scrolls on
    if (moved.clientY < 40) scrollBy(0, -16);
    else if (moved.clientY > innerHeight - 40) scrollBy(0, 16);
    const over = slots.find((one) => {
      const card = one.getBoundingClientRect();
      return one !== slot && moved.clientX >= card.left && moved.clientX <= card.right && moved.clientY >= card.top && moved.clientY <= card.bottom;
    });
    if (!over) return;
    const card = over.getBoundingClientRect();
    // over the upper left of a card the hole goes before it, else after it
    const before = (moved.clientX - card.left) / card.width + (moved.clientY - card.top) / card.height < 1;
    const rest = slots.filter((one) => one !== slot).sort(byOrder);
    rest.splice(rest.indexOf(over) + (before ? 0 : 1), 0, hole);
    rest.forEach((one, place) => (one.style.order = place));
  };
  const end = () => {
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", end);
    removeEventListener("pointercancel", end);
    slot.removeEventListener("lostpointercapture", end);
    slot.classList.remove("lifted");
    Object.assign(slot.style, { width: "", left: "", top: "", order: hole.style.order });
    hole.remove();
    slots.sort(byOrder);
    if (keys(slots) !== was) save(board, slots);
  };
  addEventListener("pointermove", move);
  addEventListener("pointerup", end);
  addEventListener("pointercancel", end);
  slot.addEventListener("lostpointercapture", end);
});
