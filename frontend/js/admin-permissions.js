export function permissionSet(user) {
  return new Set(user?.permissions || []);
}


export function hasPermission(user, permission) {
  return permissionSet(user).has(permission);
}


export function applyPermissionVisibility(user, root = document) {
  const permissions = permissionSet(user);
  root.querySelectorAll('[data-permission]').forEach((element) => {
    const required = element.dataset.permission;
    element.classList.toggle('hidden', !permissions.has(required));
  });
}


export function permittedViews(user, root = document) {
  const permissions = permissionSet(user);
  return [...root.querySelectorAll('[data-admin-view]')]
    .filter((element) => permissions.has(element.dataset.permission))
    .map((element) => element.dataset.adminView);
}
