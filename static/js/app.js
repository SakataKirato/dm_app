document.addEventListener('DOMContentLoaded', () => {
  const pageJumps = [...document.querySelectorAll('.page-jump')];
  const closePageJump = (pageJump) => {
    pageJump.querySelector('button').hidden = false;
    pageJump.querySelector('form').hidden = true;
  };

  pageJumps.forEach((pageJump) => {
    const button = pageJump.querySelector('button');
    const form = pageJump.querySelector('form');
    const input = form.querySelector('input[type="number"]');
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      pageJumps.forEach((otherPageJump) => {
        if (otherPageJump !== pageJump) closePageJump(otherPageJump);
      });
      button.hidden = true;
      form.hidden = false;
      input.focus();
    });
    form.addEventListener('click', (event) => event.stopPropagation());
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closePageJump(pageJump);
    });
  });
  document.addEventListener('click', () => pageJumps.forEach(closePageJump));

  const form = document.querySelector('.filter-panel form');
  if (!form) return;
  const arenaSelect = form.querySelector('#arena-filter');
  const categorySelect = form.querySelector('#category-filter');
  const dateSelect = form.querySelector('#date-filter');
  const categoriesByArena = JSON.parse(form.dataset.categoriesByArena || '{}');
  const datesByArenaCategory = JSON.parse(form.dataset.datesByArenaCategory || '{}');
  const arenaOptions = JSON.parse(form.dataset.arenaOptions || '[]');
  const arenasByName = Object.fromEntries(arenaOptions.map((arena) => [arena.name, arena]));
  const styleVariants = {
    text: 'text_style_control', search: 'search_style_control',
    vision: 'vision_style_control', document: 'document_style_control',
  };
  const arenaPicker = form.querySelector('[data-arena-picker]');
  const styleToggle = form.querySelector('#style-control-toggle');

  const updateCategoryOptions = () => {
    const selectedCategory = categorySelect.value;
    const categories = categoriesByArena[arenaSelect.value] || [];
    categorySelect.replaceChildren();
    categories.forEach((category, index) => {
      categorySelect.add(new Option(
        category, category, false, category === selectedCategory || (!categories.includes(selectedCategory) && index === 0)
      ));
    });
  };

  const updateDateOptions = (selectLatest = false) => {
    const selectedDate = dateSelect.value;
    const dates = datesByArenaCategory[arenaSelect.value]?.[categorySelect.value] || [];
    dateSelect.replaceChildren();
    dates.forEach((date, index) => {
      const isSelected = selectLatest
        ? index === 0
        : date === selectedDate || (!dates.includes(selectedDate) && index === 0);
      dateSelect.add(new Option(
        date, date, false, isSelected
      ));
    });
  };

  const syncArenaPicker = () => {
    if (!arenaPicker) return;
    const selectedArena = arenaOptions.find((arena) => String(arena.id) === arenaSelect.value);
    if (!selectedArena) return;
    const isStyleControl = selectedArena.name.endsWith('_style_control');
    const baseArena = isStyleControl
      ? selectedArena.name.replace('_style_control', '')
      : selectedArena.name;
    const hasStyleVariant = Boolean(styleVariants[baseArena] && arenasByName[styleVariants[baseArena]]);
    styleToggle.checked = isStyleControl;
    styleToggle.disabled = !hasStyleVariant;
    arenaPicker.querySelectorAll('[data-arena-base]').forEach((button) => {
      button.classList.toggle('active', button.dataset.arenaBase === baseArena);
    });
    arenaPicker.querySelectorAll('.arena-group').forEach((group) => {
      group.classList.toggle('has-active', Boolean(group.querySelector('[data-arena-base].active')));
    });
  };

  const setArena = (baseArena) => {
    const styleArena = styleVariants[baseArena];
    const arenaName = styleToggle.checked && styleArena && arenasByName[styleArena]
      ? styleArena
      : baseArena;
    const arena = arenasByName[arenaName];
    if (!arena) return;
    arenaSelect.value = String(arena.id);
    arenaSelect.dispatchEvent(new Event('change'));
  };

  if (arenaPicker) {
    arenaPicker.querySelectorAll('[data-arena-base]').forEach((button) => {
      button.addEventListener('click', () => setArena(button.dataset.arenaBase));
    });
    arenaPicker.querySelectorAll('.arena-trigger').forEach((trigger) => {
      trigger.addEventListener('click', () => trigger.parentElement.classList.toggle('open'));
    });
    styleToggle.addEventListener('change', () => {
      const selectedArena = arenaOptions.find((arena) => String(arena.id) === arenaSelect.value);
      const baseArena = selectedArena.name.replace('_style_control', '');
      setArena(baseArena);
    });
    document.addEventListener('click', (event) => {
      if (!arenaPicker.contains(event.target)) {
        arenaPicker.querySelectorAll('.arena-group.open').forEach((group) => group.classList.remove('open'));
      }
    });
  }

  arenaSelect.addEventListener('change', () => {
    updateCategoryOptions();
    updateDateOptions(true);
    syncArenaPicker();
  });
  categorySelect.addEventListener('change', () => updateDateOptions(true));
  syncArenaPicker();
});
