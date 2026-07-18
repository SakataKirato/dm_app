document.addEventListener('DOMContentLoaded', () => {
  const closePageJumps = () => {
    document.querySelectorAll('.page-jump').forEach((pageJump) => {
      pageJump.querySelector('button').hidden = false;
      pageJump.querySelector('form').hidden = true;
    });
  };

  document.addEventListener('click', (event) => {
    const ellipsis = event.target.closest('.page-jump .ellipsis');
    if (ellipsis) {
      event.stopPropagation();
      closePageJumps();
      const pageJump = ellipsis.closest('.page-jump');
      ellipsis.hidden = true;
      pageJump.querySelector('form').hidden = false;
      pageJump.querySelector('input[type="number"]').focus();
      return;
    }
    if (!event.target.closest('.page-jump form')) closePageJumps();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && event.target.matches('.page-jump input')) closePageJumps();
  });

  let form = document.querySelector('.filter-panel form');
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
  let resultsSection = document.querySelector('.results-section');
  let isLoading = false;
  const isMainLeaderboard = form.hasAttribute('data-main-leaderboard');
  const isAggregateLeaderboard = form.hasAttribute('data-aggregate-leaderboard');

  const updateCategoryOptions = () => {
    const selectedCategory = categorySelect.value;
    const categories = categoriesByArena[arenaSelect.value] || [];
    categorySelect.replaceChildren();
    categories.forEach((category, index) => {
      categorySelect.add(new Option(
        category, category, false,
        category === selectedCategory || (!categories.includes(selectedCategory) && index === 0)
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
      dateSelect.add(new Option(date, date, false, isSelected));
    });
  };

  const syncArenaPicker = () => {
    if (!arenaPicker) return;
    const selectedArena = arenaOptions.find((arena) => String(arena.id) === arenaSelect.value);
    if (!selectedArena) return;
    const isStyleControl = selectedArena.name.endsWith('_style_control');
    const baseArena = isStyleControl ? selectedArena.name.replace('_style_control', '') : selectedArena.name;
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
    const arenaName = styleToggle.checked && styleArena && arenasByName[styleArena] ? styleArena : baseArena;
    const arena = arenasByName[arenaName];
    if (!arena) return;
    arenaSelect.value = String(arena.id);
    arenaSelect.dispatchEvent(new Event('change'));
  };

  const syncFilterValues = (filters) => {
    form.elements.q.value = filters.q || '';
    form.elements.organization.value = filters.organization || '';
    form.elements.license.value = filters.license || '';
    arenaSelect.value = String(filters.arena);
    updateCategoryOptions();
    categorySelect.value = filters.category;
    updateDateOptions();
    dateSelect.value = filters.date;
    syncArenaPicker();
  };

  const syncAggregateFilterValues = (nextForm) => {
    arenaSelect.value = nextForm.elements.arena.value;
    updateCategoryOptions();
    categorySelect.value = nextForm.elements.category.value;
    updateDateOptions();
    dateSelect.value = nextForm.elements.date.value;
    syncArenaPicker();
  };

  const loadLeaderboard = async (url, pushHistory = true) => {
    if (isLoading) return;
    const targetUrl = new URL(url, window.location.origin);
    const apiUrl = new URL('api/leaderboard', form.action || window.location.href);
    apiUrl.search = targetUrl.search;
    isLoading = true;
    resultsSection.classList.add('is-loading');
    try {
      const response = await fetch(apiUrl, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('Request failed');
      const payload = await response.json();
      resultsSection.outerHTML = payload.html;
      resultsSection = document.querySelector('.results-section');
      syncFilterValues(payload.filters);
      if (pushHistory) history.pushState({}, '', `${targetUrl.pathname}${targetUrl.search}`);
    } catch (_error) {
      window.location.assign(targetUrl);
    } finally {
      isLoading = false;
    }
  };

  const loadAggregateLeaderboard = async (url, pushHistory = true) => {
    if (isLoading) return;
    const targetUrl = new URL(url, window.location.origin);
    isLoading = true;
    resultsSection.classList.add('is-loading');
    try {
      const response = await fetch(targetUrl, { headers: { Accept: 'text/html' } });
      if (!response.ok) throw new Error('Request failed');
      const documentResponse = new DOMParser().parseFromString(await response.text(), 'text/html');
      const nextResults = documentResponse.querySelector('.results-section');
      const nextForm = documentResponse.querySelector('.filter-panel form');
      if (!nextResults || !nextForm) throw new Error('Results not found');
      resultsSection.outerHTML = nextResults.outerHTML;
      resultsSection = document.querySelector('.results-section');
      syncAggregateFilterValues(nextForm);
      if (pushHistory) history.pushState({}, '', `${targetUrl.pathname}${targetUrl.search}`);
    } catch (_error) {
      window.location.assign(targetUrl);
    } finally {
      isLoading = false;
    }
  };

  form.addEventListener('submit', (event) => {
    if (!isMainLeaderboard && !isAggregateLeaderboard) return;
    event.preventDefault();
    const targetUrl = new URL(form.action || window.location.href, window.location.origin);
    targetUrl.search = new URLSearchParams(new FormData(form)).toString();
    if (isMainLeaderboard) loadLeaderboard(targetUrl);
    else loadAggregateLeaderboard(targetUrl);
  });

  document.addEventListener('click', (event) => {
    const link = event.target.closest('.results-section .sort-link, .results-section .pagination a');
    if ((isMainLeaderboard || isAggregateLeaderboard) && link) {
      event.preventDefault();
      if (isMainLeaderboard) loadLeaderboard(link.href);
      else loadAggregateLeaderboard(link.href);
    }
    const resetLink = event.target.closest('.filter-actions a');
    if ((isMainLeaderboard || isAggregateLeaderboard) && resetLink) {
      event.preventDefault();
      if (isMainLeaderboard) loadLeaderboard(resetLink.href);
      else loadAggregateLeaderboard(resetLink.href);
    }
    if (arenaPicker) {
      if (!arenaPicker.contains(event.target)) {
        arenaPicker.querySelectorAll('.arena-group.open').forEach((group) => group.classList.remove('open'));
      } else if (!event.target.closest('.arena-group')) {
        arenaPicker.classList.add('dismiss-hover');
        arenaPicker.querySelectorAll('.arena-group.open').forEach((group) => group.classList.remove('open'));
      }
    }
  });
  document.addEventListener('submit', (event) => {
    if (!event.target.matches('.page-jump form')) return;
    if (!isMainLeaderboard && !isAggregateLeaderboard) return;
    event.preventDefault();
    const targetUrl = new URL(form.action || window.location.href, window.location.origin);
    targetUrl.search = new URLSearchParams(new FormData(event.target)).toString();
    if (isMainLeaderboard) loadLeaderboard(targetUrl);
    else loadAggregateLeaderboard(targetUrl);
  });
  if (isMainLeaderboard || isAggregateLeaderboard) {
    window.addEventListener('popstate', () => {
      if (isMainLeaderboard) loadLeaderboard(window.location.href, false);
      else loadAggregateLeaderboard(window.location.href, false);
    });
  }

  if (arenaPicker) {
    const closeOtherArenaGroups = (currentGroup) => {
      arenaPicker.querySelectorAll('.arena-group.open').forEach((group) => {
        if (group !== currentGroup) group.classList.remove('open');
      });
    };
    arenaPicker.querySelectorAll('.arena-group').forEach((group) => {
      group.addEventListener('mouseenter', () => closeOtherArenaGroups(group));
    });
    arenaPicker.querySelectorAll('[data-arena-base]').forEach((button) => {
      button.addEventListener('click', () => {
        setArena(button.dataset.arenaBase);
        arenaPicker.classList.add('dismiss-hover');
        button.closest('.arena-group').classList.remove('open');
      });
    });
    arenaPicker.querySelectorAll('.arena-trigger').forEach((trigger) => {
      trigger.addEventListener('click', () => {
        arenaPicker.classList.remove('dismiss-hover');
        closeOtherArenaGroups(trigger.parentElement);
        trigger.parentElement.classList.toggle('open');
      });
    });
    arenaPicker.addEventListener('mouseleave', () => arenaPicker.classList.remove('dismiss-hover'));
    styleToggle.addEventListener('change', () => {
      const selectedArena = arenaOptions.find((arena) => String(arena.id) === arenaSelect.value);
      setArena(selectedArena.name.replace('_style_control', ''));
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
