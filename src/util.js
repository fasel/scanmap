// Convenience function to create HTML elements
function el(spec) {
  let pa = document.createElement(spec.tag);
  let children = spec.children || [];
  delete spec.tag;
  delete spec.children;

  let events = spec.on || {};
  Object.keys(events).forEach((ev) => {
    pa.addEventListener(ev, events[ev]);
  });
  delete spec.on;

  let dataset = spec.dataset || {};
  Object.keys(dataset).forEach((k) => {
    pa.dataset[k] = dataset[k];
  });
  delete spec.dataset;

  Object.keys(spec).forEach((k) => {
    pa[k] = spec[k];
  });

  children.forEach((ch) => {
    let e = ch instanceof HTMLElement ? ch : el(ch);
    pa.appendChild(e);
  });
  return pa;
}

// Interface to the backend
const api = {
  authKey: '',

  get(url, onSuccess) {
    return fetch(url, {
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-AUTH': this.authKey
      },
      method: 'GET'
    })
      .then((res) => {
        if (!res.ok) {
          if (res.status == 401) {
            throw new Error('Unauthorized');
          } else {
            throw new Error(`Response ${res.status}`);
          }
        }
        return res.json();
      })
      .then(onSuccess);
  },

  post(url, data, onSuccess) {
    let form = data instanceof FormData;
    let headers = {
        'X-AUTH': this.authKey,
        'Accept': 'application/json',
    };
    if (!form) headers['Content-Type'] = 'application/json';
    return fetch(url, {
      headers: headers,
      method: 'POST',
      body: form ? data : JSON.stringify(data)
    })
      .then((res) => {
        if (!res.ok) {
          if (res.status == 401) {
            throw new Error('Unauthorized');
          } else {
            throw new Error(`Response ${res.status}`);
          }
        }
        return res.json();
      })
      .then(onSuccess);
  }
};

export {api, el};
