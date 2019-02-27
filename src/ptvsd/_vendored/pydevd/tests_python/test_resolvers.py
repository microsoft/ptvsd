from tests_python.debug_constants import IS_PY2


def check_len_entry(len_entry, first_2_params):
    assert len_entry[:2] == first_2_params
    assert callable(len_entry[2])
    assert len_entry[2]('check') == 'len(check)'


def test_dict_resolver():
    from _pydevd_bundle.pydevd_resolver import DictResolver
    dict_resolver = DictResolver()
    dct = {(1, 2): 2, u'22': 22}
    contents_debug_adapter_protocol = dict_resolver.get_contents_debug_adapter_protocol(dct)
    len_entry = contents_debug_adapter_protocol.pop(-1)
    check_len_entry(len_entry, ('__len__', 2))
    if IS_PY2:
        assert contents_debug_adapter_protocol == [
            ('(1, 2)', 2, '[(1, 2)]'), (u"u'22'", 22, u"[u'22']")]
    else:
        assert contents_debug_adapter_protocol == [
            ("'22'", 22, "['22']"), ('(1, 2)', 2, '[(1, 2)]')]


def test_tuple_resolver():
    from _pydevd_bundle.pydevd_resolver import TupleResolver
    tuple_resolver = TupleResolver()
    lst = tuple(range(11))
    contents_debug_adapter_protocol = tuple_resolver.get_contents_debug_adapter_protocol(lst)
    len_entry = contents_debug_adapter_protocol.pop(-1)
    assert contents_debug_adapter_protocol == [
        ('00', 0, '[0]'),
        ('01', 1, '[1]'),
        ('02', 2, '[2]'),
        ('03', 3, '[3]'),
        ('04', 4, '[4]'),
        ('05', 5, '[5]'),
        ('06', 6, '[6]'),
        ('07', 7, '[7]'),
        ('08', 8, '[8]'),
        ('09', 9, '[9]'),
        ('10', 10, '[10]'),
    ]
    check_len_entry(len_entry, ('__len__', 11))

    assert tuple_resolver.get_dictionary(lst) == {
        '00': 0,
        '01': 1,
        '02': 2,
        '03': 3,
        '04': 4,
        '05': 5,
        '06': 6,
        '07': 7,
        '08': 8,
        '09': 9,
        '10': 10,
        '__len__': 11
    }

    lst = tuple(range(10))
    contents_debug_adapter_protocol = tuple_resolver.get_contents_debug_adapter_protocol(lst)
    len_entry = contents_debug_adapter_protocol.pop(-1)
    assert contents_debug_adapter_protocol == [
        ('0', 0, '[0]'),
        ('1', 1, '[1]'),
        ('2', 2, '[2]'),
        ('3', 3, '[3]'),
        ('4', 4, '[4]'),
        ('5', 5, '[5]'),
        ('6', 6, '[6]'),
        ('7', 7, '[7]'),
        ('8', 8, '[8]'),
        ('9', 9, '[9]'),
    ]
    check_len_entry(len_entry, ('__len__', 10))

    assert tuple_resolver.get_dictionary(lst) == {
        '0': 0,
        '1': 1,
        '2': 2,
        '3': 3,
        '4': 4,
        '5': 5,
        '6': 6,
        '7': 7,
        '8': 8,
        '9': 9,
        '__len__': 10
    }

