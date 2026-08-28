import server.main as main


def pytest_configure(config):
    main.supabase = None
