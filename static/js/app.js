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

  arenaSelect.addEventListener('change', () => {
    updateCategoryOptions();
    updateDateOptions(true);
  });
  categorySelect.addEventListener('change', () => updateDateOptions(true));
});
