/*
  ErrorBoundary.jsx   catches uncaught JS errors anywhere in the render
  tree below it (React error boundaries only catch class components —
  there's no hook equivalent) and shows ErrorPage instead of a blank
  white screen.
*/
import { Component } from 'react'
import ErrorPage from './ErrorPage'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught:', error, info?.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorPage
          kind="crash"
          detail={import.meta.env.DEV ? String(this.state.error?.stack || this.state.error) : ''}
          onRetry={() => window.location.reload()}
          onGoHome={() => {
            this.setState({ error: null })
            window.location.href = '/'
          }}
        />
      )
    }
    return this.props.children
  }
}
