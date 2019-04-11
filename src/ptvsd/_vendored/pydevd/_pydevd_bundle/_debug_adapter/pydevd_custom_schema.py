from .pydevd_base_schema import BaseSchema, register, register_request, register_response

@register_request('setDebuggerProperty')
@register
class SetDebuggerPropertyRequest(BaseSchema):
    """
    The request sets a debugger setting.
    """

    __props__ = {
        "seq": {
            "type": "integer",
            "description": "Sequence number."
        },
        "type": {
            "type": "string",
            "enum": [
                "request"
            ]
        },
        "command": {
            "type": "string",
            "enum": [
                "setDebuggerProperty"
            ]
        },
        "arguments": {
            "type": "SetDebuggerPropertyArguments"
        }
    }
    __refs__ = set(['arguments'])

    __slots__ = list(__props__.keys()) + ['kwargs']

    def __init__(self, arguments, seq=-1, update_ids_from_dap=False, **kwargs):  # noqa (update_ids_from_dap may be unused)
        """
        :param string type: 
        :param string command: 
        :param SetDebuggerPropertyArguments arguments: 
        :param integer seq: Sequence number.
        """
        self.type = 'request'
        self.command = 'setDebuggerProperty'
        if arguments is None:
            self.arguments = SetDebuggerPropertyArguments()
        else:
            self.arguments = SetDebuggerPropertyArguments(update_ids_from_dap=update_ids_from_dap, **arguments) if arguments.__class__ !=  SetDebuggerPropertyArguments else arguments
        self.seq = seq
        self.kwargs = kwargs


    def to_dict(self, update_ids_to_dap=False):  # noqa (update_ids_to_dap may be unused)
        type = self.type  # noqa (assign to builtin)
        command = self.command
        arguments = self.arguments
        seq = self.seq
        dct = {
            'type': type,
            'command': command,
            'arguments': arguments.to_dict(update_ids_to_dap=update_ids_to_dap),
            'seq': seq,
        }
        dct.update(self.kwargs)
        return dct


@register
class SetDebuggerPropertyArguments(BaseSchema):
    """
    Arguments for 'setDebuggerProperty' request.
    """

    __props__ = {}

    __refs__ = set()

    __slots__ = list(__props__.keys()) + ['kwargs']

    def __init__(self, update_ids_from_dap=False, **kwargs):  # noqa (update_ids_from_dap may be unused)
        self.kwargs = kwargs


    def to_dict(self, update_ids_to_dap=False):  # noqa (update_ids_to_dap may be unused)
        dct = {}
        dct.update(self.kwargs)
        return dct


@register_response('setDebuggerProperty')
@register
class SetDebuggerPropertyResponse(BaseSchema):
    """
    Response to 'setDebuggerProperty' request. This is just an acknowledgement, so no body field is required.
    """

    __props__ = {
        "seq": {
            "type": "integer",
            "description": "Sequence number."
        },
        "type": {
            "type": "string",
            "enum": [
                "response"
            ]
        },
        "request_seq": {
            "type": "integer",
            "description": "Sequence number of the corresponding request."
        },
        "success": {
            "type": "boolean",
            "description": "Outcome of the request."
        },
        "command": {
            "type": "string",
            "description": "The command requested."
        },
        "message": {
            "type": "string",
            "description": "Contains error message if success == false."
        },
        "body": {
            "type": [
                "array",
                "boolean",
                "integer",
                "null",
                "number",
                "object",
                "string"
            ],
            "description": "Contains request result if success is true and optional error details if success is false."
        }
    }
    __refs__ = set()

    __slots__ = list(__props__.keys()) + ['kwargs']

    def __init__(self, request_seq, success, command, seq=-1, message=None, body=None, update_ids_from_dap=False, **kwargs):  # noqa (update_ids_from_dap may be unused)
        """
        :param string type: 
        :param integer request_seq: Sequence number of the corresponding request.
        :param boolean success: Outcome of the request.
        :param string command: The command requested.
        :param integer seq: Sequence number.
        :param string message: Contains error message if success == false.
        :param ['array', 'boolean', 'integer', 'null', 'number', 'object', 'string'] body: Contains request result if success is true and optional error details if success is false.
        """
        self.type = 'response'
        self.request_seq = request_seq
        self.success = success
        self.command = command
        self.seq = seq
        self.message = message
        self.body = body
        self.kwargs = kwargs


    def to_dict(self, update_ids_to_dap=False):  # noqa (update_ids_to_dap may be unused)
        type = self.type  # noqa (assign to builtin)
        request_seq = self.request_seq
        success = self.success
        command = self.command
        seq = self.seq
        message = self.message
        body = self.body
        dct = {
            'type': type,
            'request_seq': request_seq,
            'success': success,
            'command': command,
            'seq': seq,
        }
        if message is not None:
            dct['message'] = message
        if body is not None:
            dct['body'] = body
        dct.update(self.kwargs)
        return dct
