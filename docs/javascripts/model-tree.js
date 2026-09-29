/* Interactive browser for the metadata model (docs/model.md).
 *
 * Reads the imaging model's paths as scripts/sync_docs_data.py writes them
 * from the packaged model, so the page never lists fields by hand: plain
 * nested JSON where every leaf is "FieldName": "range".
 */
(function () {
  'use strict';

  function isLeaf(value) {
    return typeof value === 'string';
  }

  /* Flatten a model into {path: type}, the form the converter targets. */
  function leaves(node, prefix, out) {
    out = out || {};
    Object.keys(node).forEach(function (key) {
      var path = prefix ? prefix + '.' + key : key;
      if (isLeaf(node[key])) {
        out[path] = node[key];
      } else {
        leaves(node[key], path, out);
      }
    });
    return out;
  }

  function countFields(node) {
    return Object.keys(leaves(node, '')).length;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /* One <li> per model entry; groups nest another <ul> below their header. */
  function buildNode(key, value, path, added, targets) {
    var item = el('li', 'mt-item');
    item.dataset.path = path;

    var row = el('div', 'mt-row');
    var leaf = isLeaf(value);

    if (leaf) {
      row.appendChild(el('span', 'mt-bullet', '·'));
    } else {
      var toggle = el('button', 'mt-toggle');
      toggle.type = 'button';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Toggle ' + path);
      toggle.addEventListener('click', function () {
        setOpen(item, !item.classList.contains('mt-open'));
      });
      row.appendChild(toggle);
    }

    var name = el('span', 'mt-name', key);
    name.title = path + ' (click to copy)';
    name.addEventListener('click', function () {
      copyPath(path, name);
    });
    row.appendChild(name);

    if (leaf) {
      row.appendChild(el('span', 'mt-type mt-type-' + value, value));
    } else {
      row.appendChild(el('span', 'mt-count', countFields(value) + ' fields'));
    }

    if (leaf && added[path]) {
      row.appendChild(el('span', 'mt-flag mt-flag-ext', 'extension'));
      item.dataset.extended = 'true';
    }
    if (targets && targets[path]) {
      var sources = targets[path];
      var mapped = el('span', 'mt-flag mt-flag-mapped',
                      sources.length === 1 ? 'mapped' : sources.length + ' mappings');
      mapped.title = 'Mapped from: ' + sources.join(', ');
      row.appendChild(mapped);
      item.dataset.mapped = 'true';
    }

    item.appendChild(row);

    if (!leaf) {
      var children = el('ul', 'mt-children');
      children.style.display = 'none';   /* every group starts collapsed */
      Object.keys(value).forEach(function (childKey) {
        children.appendChild(buildNode(
          childKey, value[childKey], path + '.' + childKey,
          added, targets));
      });
      item.appendChild(children);
    }
    return item;
  }

  function childList(item) {
    var children = item.children;
    for (var i = 0; i < children.length; i += 1) {
      if (children[i].classList.contains('mt-children')) return children[i];
    }
    return null;
  }

  /* Expansion is driven by an inline style rather than a stylesheet rule, so
   * it cannot be out-specified by the theme's own list styling - and the tree
   * still opens and closes if model-tree.css fails to load at all. */
  function setOpen(item, open) {
    var children = childList(item);
    if (!children) return;
    item.classList.toggle('mt-open', open);
    children.style.display = open ? 'block' : 'none';
    var toggle = item.querySelector('.mt-row > .mt-toggle');
    if (toggle && toggle.parentElement.parentElement === item) {
      toggle.setAttribute('aria-expanded', String(open));
    }
  }

  function copyPath(path, node) {
    var done = function () {
      node.classList.add('mt-copied');
      setTimeout(function () { node.classList.remove('mt-copied'); }, 900);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(path).then(done, function () {});
    }
  }

  /* Map each model target path to the source paths mappings.json sends to it,
   * so the tree shows which fields a conversion can actually populate. A rule
   * can name several targets. A per-item target (Pixels.Channel[*].Fluorophore
   * .EmissionWavelength) runs through classes with their own place in the
   * tree, the top-level keys, so it is shown from the last one it passes. */
  function mappingTargets(mappings, model) {
    var targets = {};
    Object.keys(mappings || {}).forEach(function (source) {
      [].concat(mappings[source]).forEach(function (rule) {
        var parts = String(rule).replace(/\[\]$/, '').replace(/\[\*\]/g, '').split('.');
        var start = 0;
        if (String(rule).indexOf('[*]') >= 0) {
          parts.forEach(function (part, index) {
            if (index > 0 && model.hasOwnProperty(part)) start = index;
          });
        }
        var target = parts.slice(start).join('.');
        if (!targets[target]) targets[target] = [];
        targets[target].push(source);
      });
    });
    return targets;
  }

  function applyFilter(tree, query, onlyExtended, onlyMapped) {
    var needle = query.trim().toLowerCase();
    var filtering = !!needle || onlyExtended || onlyMapped;
    var shown = 0;

    function visit(item) {
      var children = childList(item);
      var kidMatched = false;
      if (children) {
        Array.prototype.forEach.call(children.children, function (kid) {
          kidMatched = visit(kid) || kidMatched;
        });
      }

      var self = !needle || item.dataset.path.toLowerCase().indexOf(needle) >= 0;
      /* Only leaves are extensions; a group is a container, not a field. But a
       * group can be a mapping target in its own right, since a "Prefix.*" or
       * "Target[]" rule fills a whole subtree, so it stays under Mapped only. */
      if (onlyExtended && item.dataset.extended !== 'true') self = false;
      if (onlyMapped && item.dataset.mapped !== 'true') self = false;
      if (children && onlyExtended) self = false;

      var visible = self || kidMatched;
      item.style.display = visible ? '' : 'none';
      item.classList.toggle('mt-match', self && filtering);
      if (filtering && kidMatched) setOpen(item, true);
      if (self && !children) shown += 1;
      return visible;
    }

    Array.prototype.forEach.call(tree.children, visit);
    return shown;
  }

  function init(container) {
    var status = el('p', 'mt-status', 'Loading model…');
    container.appendChild(status);

    var wanted = [
      container.dataset.model,
      container.dataset.added,
      container.dataset.mappings
    ];

    Promise.all(wanted.map(function (url) {
      return fetch(url).then(function (response) {
        if (!response.ok) throw new Error(url + ': ' + response.status);
        return response.json();
      });
    })).then(function (loaded) {
      render(container, status, loaded[0], loaded[1], loaded[2]);
    }).catch(function (error) {
      /* Say so on the page: a silent half-built tree is the hard thing to
       * diagnose, since the controls are there but nothing responds. */
      status.textContent = 'Model browser failed: ' + error.message;
      status.classList.add('mt-error');
      if (window.console) window.console.error(error);
    });
  }

  function render(container, status, model, addedPaths, mappings) {
    var added = {};
    addedPaths.forEach(function (path) { added[path] = true; });
    var targets = mappingTargets(mappings, model);

    var controls = el('div', 'mt-controls');

    var search = el('input', 'mt-search');
    search.type = 'search';
    search.placeholder = 'Filter by path, e.g. Pixels.Size or Vacuum';
    search.setAttribute('aria-label', 'Filter model fields');

    var extendedBox = el('input');
    extendedBox.type = 'checkbox';
    var extendedOnly = el('label', 'mt-check');
    extendedOnly.appendChild(extendedBox);
    extendedOnly.appendChild(el('span', null, 'Extensions only'));

    var mappedBox = el('input');
    mappedBox.type = 'checkbox';
    var mappedOnly = el('label', 'mt-check');
    mappedOnly.appendChild(mappedBox);
    mappedOnly.appendChild(el('span', null, 'Mapped only'));

    var expand = el('button', 'mt-button', 'Expand all');
    expand.type = 'button';
    var collapse = el('button', 'mt-button', 'Collapse all');
    collapse.type = 'button';

    [search, extendedOnly, mappedOnly, expand, collapse]
      .forEach(function (node) { controls.appendChild(node); });

    var tree = el('ul', 'mt-tree');
    container.insertBefore(controls, status);
    container.appendChild(tree);

    function refresh() {
      var shown = applyFilter(
        tree, search.value, extendedBox.checked, mappedBox.checked);
      var total = countFields(model);
      status.textContent = shown === total
        ? total + ' fields'
        : shown + ' of ' + total + ' fields';
    }

    /* #Image.Pixels.SizeX in the URL opens and scrolls to that field. */
    function openFromHash() {
      var path = decodeURIComponent(window.location.hash.replace(/^#/, ''));
      if (!path) return;
      var match = null;
      Array.prototype.forEach.call(
        tree.querySelectorAll('.mt-item'), function (item) {
          if (item.dataset.path === path) match = item;
          item.classList.remove('mt-target');
        });
      if (!match) return;
      for (var node = match; node && node !== tree; node = node.parentElement) {
        if (node.classList && node.classList.contains('mt-item')) {
          setOpen(node, true);
        }
      }
      match.classList.add('mt-target');
      match.scrollIntoView({ block: 'center' });
    }

    function draw() {
      tree.textContent = '';
      Object.keys(model).forEach(function (key) {
        tree.appendChild(buildNode(key, model[key], key, added, targets));
      });
      refresh();
      openFromHash();
    }

    var typing;
    search.addEventListener('input', function () {
      clearTimeout(typing);
      typing = setTimeout(refresh, 120);
    });
    [extendedBox, mappedBox].forEach(function (node) {
      node.addEventListener('change', refresh);
    });
    expand.addEventListener('click', function () {
      Array.prototype.forEach.call(
        tree.querySelectorAll('.mt-item'), function (item) {
          if (childList(item)) setOpen(item, true);
        });
    });
    collapse.addEventListener('click', function () {
      Array.prototype.forEach.call(
        tree.querySelectorAll('.mt-item'), function (item) {
          setOpen(item, false);
        });
    });
    window.addEventListener('hashchange', openFromHash);

    draw();
  }

  function boot() {
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-model-tree]'), function (container) {
        if (container.dataset.ready) return;
        container.dataset.ready = 'true';
        init(container);
      });
  }

  /* Material ships instant navigation, so re-run per page load as well. */
  if (window.document$ && typeof window.document$.subscribe === 'function') {
    window.document$.subscribe(boot);
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
