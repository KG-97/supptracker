import AppComponent, { DEFAULT_STACK_EXAMPLE as SOURCE_DEFAULT_STACK_EXAMPLE } from './src/App'

export const DEFAULT_STACK_EXAMPLE = 'creatine, caffeine, magnesium'

if (DEFAULT_STACK_EXAMPLE !== SOURCE_DEFAULT_STACK_EXAMPLE) {
  throw new Error('DEFAULT_STACK_EXAMPLE mismatch between entrypoints')
}

export default AppComponent
export { SOURCE_DEFAULT_STACK_EXAMPLE }
