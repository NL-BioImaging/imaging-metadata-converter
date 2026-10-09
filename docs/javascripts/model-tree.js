/* Interactive browser for the metadata model (docs/model.md).
 *
 * Reads the imaging model's paths as scripts/docs_data.py builds them
 * from the packaged model, so the page never lists fields by hand: plain
 * nested JSON where every leaf is "FieldName": "range", and, per path, what
 * the model says of it beyond its range (data/details.json).
 *
 * The tree starts at the model's root, OME: a field holding a class opens
 * that class's fields in place, and one holding an abstract class opens the
 * classes that can stand for it, so every class is reached by drilling down.
 * A path keeps the form the converter targets, starting at the nearest class
 * with its own place in model.json (Pixels.PhysicalSizeX, not
 * OME.Image.Pixels.PhysicalSizeX), so a class nested in several places shows
 * the same paths in each.
 */
(function () {
  'use strict';

  var TIERS = {1: 'required', 2: 'recommended', 3: 'optional', 4: 'optional'};

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

  function flag(kind, text, title) {
    var node = el('span', 'mt-flag mt-flag-' + kind, text);
    if (title) node.title = title;
    return node;
  }

  /* The constraints of a path at a glance; the detail panel spells them out. */
  function constraintFlags(info) {
    var flags = [];
    if (info.multivalued) flags.push(flag('list', 'list', 'Multivalued: a list of values'));
    if (info.reference) flags.push(flag('ref', 'ref', 'A reference to the ID of a ' + info.range));
    if (info.identifier) flags.push(flag('id', 'ID', 'The identifier of its class'));
    if (info.tier) {
      flags.push(flag('tier mt-tier-' + info.tier, 'T' + info.tier,
                      'LiMi tier ' + info.tier + ': ' + TIERS[info.tier]));
    }
    if (info.required) flags.push(flag('required', 'required', 'Required in the model'));
    return flags;
  }

  function classLink(name, context) {
    if (!context.model.hasOwnProperty(name)) return el('code', null, name);
    var link = el('a', null, name);
    link.href = '#' + name;
    return link;
  }

  /* One term of the detail panel; `content` is a string, a node, or a list of them. */
  function addFact(list, term, content) {
    var parts = [].concat(content).filter(Boolean);
    if (!parts.length) return;
    list.appendChild(el('dt', null, term));
    var definition = el('dd');
    parts.forEach(function (part, index) {
      if (index) definition.appendChild(document.createTextNode(', '));
      definition.appendChild(typeof part === 'string' ? el('code', null, part) : part);
    });
    list.appendChild(definition);
  }

  /* The detail panel of one path, built the first time it is opened. */
  function buildDetails(path, context) {
    var info = context.info(path);
    var panel = el('div', 'mt-details');
    if (info.description !== undefined) {
      panel.appendChild(el('p', 'mt-description', context.text(info.description)));
    }
    if (info.description_source !== undefined) {
      panel.appendChild(el('p', 'mt-source',
                           'Description from ' + context.text(info.description_source)));
    }
    var list = el('dl', 'mt-facts');
    addFact(list, 'Path', path);
    if (info.class) {
      addFact(list, 'Class', classLink(info.class, context));
    } else if (info.range) {
      addFact(list, info.reference ? 'Refers to' : 'Range', classLink(info.range, context));
    }
    if (info.tier) addFact(list, 'LiMi tier', el('span', null, info.tier + ", LiMi's " + TIERS[info.tier] + ' tier'));
    addFact(list, 'Constraints', [
      info.required && 'required',
      info.multivalued && 'multivalued',
      info.identifier && 'identifier'
    ]);
    if (info.is_a) addFact(list, 'Is a', classLink(info.is_a, context));
    if (info.declared_by) addFact(list, 'Declared by', classLink(info.declared_by, context));
    addFact(list, 'Category', info.category);
    addFact(list, 'Domain', info.domain);
    addFact(list, 'Same as in OME', info.exact_mappings);
    addFact(list, 'Close to in OME', info.close_mappings);
    addFact(list, 'Mapped from', context.targets[path]);
    panel.appendChild(list);
    return panel;
  }

  function detailsPanel(item) {
    var children = item.children;
    for (var i = 0; i < children.length; i += 1) {
      if (children[i].classList.contains('mt-details')) return children[i];
    }
    return null;
  }

  function setDetailsOpen(item, open, context) {
    var panel = detailsPanel(item);
    if (!panel && !open) return;
    if (!panel) {
      panel = buildDetails(item.dataset.path, context);
      item.insertBefore(panel, childList(item));
    }
    panel.style.display = open ? 'block' : 'none';
    item.classList.toggle('mt-details-open', open);
  }

  /* The classes a field holding `range` opens into: the class itself, or
   * the concrete classes standing for an abstract one. A reference holds an
   * ID, not the object, and a class already open above would nest forever. */
  function nestedClasses(range, info, ancestors, context) {
    if (info.reference) return [];
    var classes = context.model.hasOwnProperty(range) ? [range] : context.subclasses[range] || [];
    return classes.filter(function (name) { return !ancestors[name]; });
  }

  function withAncestor(ancestors, name) {
    var extended = Object.create(ancestors);
    extended[name] = true;
    return extended;
  }

  /* One <li> per model entry; groups nest another <ul> below their header.
   * `ancestors` names the classes open above it. */
  function buildNode(key, value, path, context, ancestors) {
    var item = el('li', 'mt-item');
    item.dataset.path = path;
    var info = context.info(path);
    if (info.tier) item.dataset.tier = String(info.tier);

    var row = el('div', 'mt-row');
    var leaf = isLeaf(value);
    var nested = leaf ? nestedClasses(value, info, ancestors, context) : [];
    if (leaf) item.dataset.field = 'true';
    /* A field holding a class opens straight onto that class's fields; one
     * holding an abstract class lists the classes standing for it first. */
    var single = nested.length === 1 && nested[0] === value;
    if (single) {
      item.dataset.nestedClass = value;
      context.reached[value] = true;
    }

    if (leaf && !nested.length) {
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
    name.title = 'Show what the model says of ' + path;
    name.addEventListener('click', function () {
      setDetailsOpen(item, !item.classList.contains('mt-details-open'), context);
    });
    row.appendChild(name);

    if (nested.length) {
      row.appendChild(el('span', 'mt-type mt-type-class', value));
      row.appendChild(el('span', 'mt-count', single
        ? countFields(context.model[value]) + ' fields'
        : nested.length + ' classes'));
    } else if (leaf && (context.model.hasOwnProperty(value) || context.subclasses[value])) {
      var range = el('a', 'mt-type mt-type-class', value);
      range.href = '#' + value;
      range.title = 'Go to ' + value;
      row.appendChild(range);
    } else if (leaf) {
      row.appendChild(el('span', 'mt-type mt-type-' + value, value));
    } else {
      row.appendChild(el('span', 'mt-count', countFields(value) + ' fields'));
    }

    constraintFlags(info).forEach(function (node) { row.appendChild(node); });

    if (leaf && context.added[path]) {
      row.appendChild(flag('ext', 'extension'));
      item.dataset.extended = 'true';
    }
    if (context.targets[path]) {
      var sources = context.targets[path];
      row.appendChild(flag('mapped', sources.length === 1 ? 'mapped' : sources.length + ' mappings',
                           'Mapped from: ' + sources.join(', ')));
      item.dataset.mapped = 'true';
    }

    var copy = el('button', 'mt-copy', 'copy');
    copy.type = 'button';
    copy.title = 'Copy ' + path;
    copy.addEventListener('click', function () {
      copyPath(path, copy);
    });
    row.appendChild(copy);

    item.appendChild(row);

    if (!leaf || nested.length) {
      var children = el('ul', 'mt-children');
      children.style.display = 'none';   /* every group starts collapsed */
      if (single) {
        appendFields(children, context.model[value], value, context, withAncestor(ancestors, value));
      } else if (nested.length) {
        nested.forEach(function (name) {
          children.appendChild(classNode(name, context, ancestors));
        });
      } else {
        appendFields(children, value, path, context, ancestors);
      }
      item.appendChild(children);
    }
    return item;
  }

  /* The fields of `node`, a class or an inline group, at `path`. */
  function appendFields(list, node, path, context, ancestors) {
    Object.keys(node).forEach(function (childKey) {
      list.appendChild(buildNode(
        childKey, node[childKey], path + '.' + childKey, context, ancestors));
    });
  }

  /* A class as an entry of its own: at the top, or standing for an abstract class. */
  function classNode(name, context, ancestors) {
    context.reached[name] = true;
    var item = buildNode(name, context.model[name], name, context, withAncestor(ancestors, name));
    item.dataset.nestedClass = name;
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
   * .EmissionWavelength) runs through classes with their own place in
   * model.json, its top-level keys, so it is shown from the last one it passes. */
  function mappingTargets(mappings, model) {
    var targets = {};
    Object.keys(mappings || {}).forEach(function (source) {
      var named = mappings[source];
      /* a rule stating the unit its source implies names its target in "target" */
      if (named && named.target) named = named.target;
      [].concat(named).forEach(function (rule) {
        var parts = String(rule).replace(/\[\]$/, '').replace(/\[\]\./g, '.').replace(/\[\*\]/g, '').split('.');
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

  /* options: query, onlyExtended, onlyMapped, maxTier (0 for any tier) and
   * searchDescriptions, with describe(path) giving the lower-case description. */
  function applyFilter(tree, options) {
    var needle = options.query.trim().toLowerCase();
    var filtering = !!needle || options.onlyExtended || options.onlyMapped || !!options.maxTier;
    var shown = {};

    function matches(path) {
      return path.toLowerCase().indexOf(needle) >= 0
        || (options.searchDescriptions && options.describe(path).indexOf(needle) >= 0);
    }

    function visit(item) {
      var children = childList(item);
      var kidMatched = false;
      if (children) {
        Array.prototype.forEach.call(children.children, function (kid) {
          kidMatched = visit(kid) || kidMatched;
        });
      }

      var self = !needle || matches(item.dataset.path);
      /* Only leaves are extensions or tiered fields; a group is a container,
       * not a field. But a group can be a mapping target in its own right,
       * since a "Prefix.*" or "Target[]" rule fills a whole subtree, so it
       * stays under Mapped only. */
      if (options.onlyExtended && item.dataset.extended !== 'true') self = false;
      if (options.onlyMapped && item.dataset.mapped !== 'true') self = false;
      if (options.maxTier && !(Number(item.dataset.tier) <= options.maxTier)) self = false;
      if (children && (options.onlyExtended || options.maxTier)) self = false;

      var visible = self || kidMatched;
      item.style.display = visible ? '' : 'none';
      item.classList.toggle('mt-match', self && filtering);
      if (filtering && kidMatched) setOpen(item, true);
      if (self && item.dataset.field) shown[item.dataset.path] = true;
      return visible;
    }

    Array.prototype.forEach.call(tree.children, visit);
    /* a class nested in several places shows its fields in each, counted once */
    return Object.keys(shown).length;
  }

  function init(container) {
    var status = el('p', 'mt-status', 'Loading model…');
    container.appendChild(status);

    var wanted = [
      container.dataset.model,
      container.dataset.added,
      container.dataset.mappings,
      container.dataset.details
    ];

    Promise.all(wanted.map(function (url) {
      return fetch(url).then(function (response) {
        if (!response.ok) throw new Error(url + ': ' + response.status);
        return response.json();
      });
    })).then(function (loaded) {
      render(container, status, loaded[0], loaded[1], loaded[2], loaded[3]);
    }).catch(function (error) {
      /* Say so on the page: a silent half-built tree is the hard thing to
       * diagnose, since the controls are there but nothing responds. */
      status.textContent = 'Model browser failed: ' + error.message;
      status.classList.add('mt-error');
      if (window.console) window.console.error(error);
    });
  }

  function checkbox(label) {
    var box = el('input');
    box.type = 'checkbox';
    var wrapper = el('label', 'mt-check');
    wrapper.appendChild(box);
    wrapper.appendChild(el('span', null, label));
    return {box: box, label: wrapper};
  }

  function render(container, status, model, addedPaths, mappings, details) {
    var added = {};
    addedPaths.forEach(function (path) { added[path] = true; });
    var ranges = leaves(model, '');
    var context = {
      model: model,
      added: added,
      targets: mappingTargets(mappings, model),
      subclasses: details.subclasses || {},
      reached: {},
      text: function (index) { return details.texts[index]; },
      info: function (path) {
        var info = details.paths[path] || {};
        if (ranges[path]) info.range = ranges[path];
        return info;
      }
    };

    var described = {};
    function describe(path) {
      if (!described.hasOwnProperty(path)) {
        var index = context.info(path).description;
        described[path] = index === undefined ? '' : context.text(index).toLowerCase();
      }
      return described[path];
    }

    var controls = el('div', 'mt-controls');

    var search = el('input', 'mt-search');
    search.type = 'search';
    search.placeholder = 'Filter by path, e.g. Pixels.Size or Vacuum';
    search.setAttribute('aria-label', 'Filter model fields');

    var descriptions = checkbox('Search descriptions');
    var extendedOnly = checkbox('Extensions only');
    var mappedOnly = checkbox('Mapped only');

    var tierSelect = el('select', 'mt-select');
    tierSelect.setAttribute('aria-label', 'Filter by LiMi tier');
    [['0', 'Any tier'], ['1', 'Tier 1'], ['2', 'Tiers 1-2'], ['3', 'Tiers 1-3']]
      .forEach(function (choice) {
        var option = el('option', null, choice[1]);
        option.value = choice[0];
        tierSelect.appendChild(option);
      });

    var expand = el('button', 'mt-button', 'Expand all');
    expand.type = 'button';
    var collapse = el('button', 'mt-button', 'Collapse all');
    collapse.type = 'button';

    [search, descriptions.label, tierSelect, extendedOnly.label, mappedOnly.label, expand, collapse]
      .forEach(function (node) { controls.appendChild(node); });

    var tree = el('ul', 'mt-tree');
    container.insertBefore(controls, status);
    container.appendChild(tree);

    function refresh() {
      var shown = applyFilter(tree, {
        query: search.value,
        onlyExtended: extendedOnly.box.checked,
        onlyMapped: mappedOnly.box.checked,
        maxTier: Number(tierSelect.value),
        searchDescriptions: descriptions.box.checked,
        describe: describe
      });
      var total = countFields(model);
      status.textContent = shown === total
        ? total + ' fields'
        : shown + ' of ' + total + ' fields';
    }

    /* #Pixels.SizeX in the URL opens, scrolls to and describes that field,
     * and #Pixels that class, where it is nested least deep. */
    function openFromHash() {
      var path = decodeURIComponent(window.location.hash.replace(/^#/, ''));
      if (!path) return;
      var match = null;
      var matchDepth = Infinity;
      Array.prototype.forEach.call(
        tree.querySelectorAll('.mt-item'), function (item) {
          item.classList.remove('mt-target');
          var depth = depthOf(item);
          if ((item.dataset.path === path || item.dataset.nestedClass === path) && depth < matchDepth) {
            match = item;
            matchDepth = depth;
          }
        });
      if (!match) return;
      for (var node = match; node && node !== tree; node = node.parentElement) {
        if (node.classList && node.classList.contains('mt-item')) {
          setOpen(node, true);
        }
      }
      match.classList.add('mt-target');
      setDetailsOpen(match, true, context);
      match.scrollIntoView({ block: 'center' });
    }

    function depthOf(item) {
      var depth = 0;
      for (var node = item; node && node !== tree; node = node.parentElement) depth += 1;
      return depth;
    }

    /* The root first, then beside it every class it does not reach. */
    function draw() {
      tree.textContent = '';
      context.reached = {};
      if (model.hasOwnProperty(details.root)) tree.appendChild(classNode(details.root, context, {}));
      Object.keys(model).forEach(function (key) {
        if (!context.reached[key]) tree.appendChild(classNode(key, context, {}));
      });
      refresh();
      openFromHash();
    }

    var typing;
    search.addEventListener('input', function () {
      clearTimeout(typing);
      typing = setTimeout(refresh, 120);
    });
    [descriptions.box, extendedOnly.box, mappedOnly.box, tierSelect].forEach(function (node) {
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
