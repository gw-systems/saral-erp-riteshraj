from functools import wraps
from .utils import log_activity_direct


def log_activity(action_category, action_type, module, description_fn=None, extra_data_fn=None):
    """
    Decorator to log a view action.

    Usage:
        @log_activity('export', 'quotation_pdf', 'projects',
                      description_fn=lambda req, kw: f'Exported PDF for quotation {kw["pk"]}')
        def quotation_pdf_view(request, pk):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)

            # Only log successful responses
            if response.status_code < 400:
                desc = (
                    description_fn(request, kwargs)
                    if description_fn
                    else f'{action_category}: {action_type}'
                )
                extra = extra_data_fn(request, kwargs) if extra_data_fn else {}

                log_activity_direct(
                    user=request.user,
                    source='web',
                    action_category=action_category,
                    action_type=action_type,
                    module=module,
                    description=desc,
                    request=request,
                    extra_data=extra,
                    status_code=response.status_code,
                )
            return response
        return wrapper
    return decorator
