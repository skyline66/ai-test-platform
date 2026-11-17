// 内置演示站逻辑。刻意保持无框架、无异步请求：用例的稳定性不该由演示站决定。
(function () {
  const page = document.body.dataset.page;

  if (page === 'login') initLogin();
  if (page === 'inventory') initInventory();

  function initLogin() {
    const form = document.getElementById('login-form');
    const err = document.getElementById('err');

    const fail = (msg) => {
      err.textContent = msg;
      err.hidden = false;
    };

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      err.hidden = true;

      const phone = document.getElementById('phone').value.trim();
      const code = document.getElementById('code').value.trim();

      if (!/^\d{11}$/.test(phone)) return fail('请输入 11 位手机号');
      if (!code) return fail('请输入验证码');
      // 演示环境的「后端」：验证码固定 123456，其余一律报错
      if (code !== '123456') return fail('验证码错误');

      sessionStorage.setItem('session', JSON.stringify({ phone }));
      window.location.href = 'inventory.html';
    });
  }

  function initInventory() {
    const CART_KEY = 'cart';

    const readCart = () => {
      try {
        const raw = localStorage.getItem(CART_KEY);
        return raw ? JSON.parse(raw) : [];
      } catch (_) {
        return [];
      }
    };
    const writeCart = (items) => localStorage.setItem(CART_KEY, JSON.stringify(items));

    const countEl = document.querySelector('[data-testid="cart-count"]');
    const dialog = document.getElementById('cart-dialog');
    const cartList = document.getElementById('cart-items');
    const cartEmpty = document.getElementById('cart-empty');
    const status = document.getElementById('checkout-status');

    const renderCount = () => {
      countEl.textContent = String(readCart().length);
    };

    const renderDialog = () => {
      const items = readCart();
      cartList.replaceChildren(
        ...items.map((name) => {
          const li = document.createElement('li');
          li.textContent = name;
          return li;
        })
      );
      cartEmpty.hidden = items.length > 0;
      status.hidden = true;
      status.textContent = '';
    };

    document.querySelectorAll('[data-add]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const items = readCart();
        items.push(btn.dataset.name);
        writeCart(items);
        renderCount();
      });
    });

    document.getElementById('cart-btn').addEventListener('click', () => {
      renderDialog();
      dialog.showModal();
    });

    document.getElementById('checkout').addEventListener('click', () => {
      const n = readCart().length;
      if (n === 0) {
        status.textContent = '购物车是空的，无法结算';
      } else {
        status.textContent = `已提交订单，共 ${n} 件商品`;
        writeCart([]);
        renderCount();
      }
      status.hidden = false;
    });

    document.getElementById('close').addEventListener('click', () => dialog.close());

    // 每条用例独立打开页面，因此每次进入都按 localStorage 现状回填
    renderCount();
  }
})();