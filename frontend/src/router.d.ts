import '@tanstack/react-router'

declare module '@tanstack/react-router' {
  interface StaticDataRouteOption {
    /** Label for this route in the app shell's breadcrumb. */
    crumb?: string
  }
}
