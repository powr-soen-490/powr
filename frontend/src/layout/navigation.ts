// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

export const PAGE_FLAGS = {
  home: 'page_home',
  orders: 'page_recommended_orders',
  forecast: 'page_forecast',
  menu: 'page_menu_mapping',
  inventory: 'page_inventory',
  settings: 'page_settings',
} as const

export type PageId = keyof typeof PAGE_FLAGS
export type PageFlag = (typeof PAGE_FLAGS)[PageId]

export interface NavigationItem {
  id: PageId
  label: string
  flag: PageFlag
}

export const PAGE_FLAG_NAMES: PageFlag[] = Object.values(PAGE_FLAGS)

export const NAV: NavigationItem[] = [
  { id: 'home', label: 'Home', flag: PAGE_FLAGS.home },
  { id: 'orders', label: 'Recommended Orders', flag: PAGE_FLAGS.orders },
  { id: 'forecast', label: 'Forecast', flag: PAGE_FLAGS.forecast },
  { id: 'menu', label: 'Menu Mapping', flag: PAGE_FLAGS.menu },
  { id: 'inventory', label: 'Inventory & Vendors', flag: PAGE_FLAGS.inventory },
  { id: 'settings', label: 'Settings', flag: PAGE_FLAGS.settings },
]

export function getVisibleNavigation(
  isEnabled: (flag: PageFlag) => boolean,
): NavigationItem[] {
  return NAV.filter(({ flag }) => isEnabled(flag))
}
