from abc import ABCMeta, abstractproperty, abstractmethod
from itertools import chain

import numpy

import gem
from gem.interpreter import evaluate
from gem.utils import cached_property

from finat.quadrature import make_quadrature


class FiniteElementBase(metaclass=ABCMeta):

    @abstractproperty
    def cell(self):
        '''The reference cell on which the element is defined.'''

    @abstractproperty
    def degree(self):
        '''The degree of the embedding polynomial space.

        In the tensor case this is a tuple.
        '''

    @abstractproperty
    def formdegree(self):
        '''Degree of the associated form (FEEC)'''

    @abstractmethod
    def entity_dofs(self):
        '''Return the map of topological entities to degrees of
        freedom for the finite element.'''

    def permutations(self):
        '''Default naive permutations. 

        This is just for making tests pass.
        Must be removed once permutations are appropriately defined for all elements.
        '''
        perm_dict = {}

        import FIAT
        if isinstance(self.cell, FIAT.reference_element.TensorProductCell):
            for dim, entity_dofs in self.entity_dofs().items():
                n, = set(len(dofs) for dofs in entity_dofs.values())
                perm = list(range(n))
                perm_dict[dim] = {}
                assert len(dim) == 2
                m0, = set(len(cone) for cone in self.cell.cells[0].topology[dim[0]].values())
                m1, = set(len(cone) for cone in self.cell.cells[1].topology[dim[1]].values())
                for i0 in range(0, numpy.math.factorial(m0)*2):
                    for i1 in range(0, numpy.math.factorial(m1)*2):
                        perm_dict[dim][(i0, i1)] = perm
        else:
            for dim, entity_dofs in self.entity_dofs().items():
                n, = set(len(dofs) for dofs in entity_dofs.values())
                perm = list(range(n))
                if dim == 0:
                    perm_dict[dim] = {0: perm}
                else:
                    m, = set(len(cone) for cone in self.cell.topology[dim].values())
                    #perm_dict[dim] = {o: perm for o in range(-m, m)}
                    perm_dict[dim] = {o: perm for o in range(0, numpy.math.factorial(m)*2)}
        return perm_dict

    @cached_property
    def _entity_closure_dofs(self):
        # Compute the nodes on the closure of each sub_entity.
        entity_dofs = self.entity_dofs()
        return {dim: {e: sorted(chain(*[entity_dofs[d][se]
                                        for d, se in sub_entities]))
                      for e, sub_entities in entities.items()}
                for dim, entities in self.cell.sub_entities.items()}

    def entity_closure_dofs(self):
        '''Return the map of topological entities to degrees of
        freedom on the closure of those entities for the finite
        element.'''
        return self._entity_closure_dofs

    @cached_property
    def _entity_support_dofs(self):
        esd = {}
        for entity_dim in self.cell.sub_entities.keys():
            beta = self.get_indices()
            zeta = self.get_value_indices()

            entity_cell = self.cell.construct_subelement(entity_dim)
            quad = make_quadrature(entity_cell, (2*numpy.array(self.degree)).tolist())

            eps = 1.e-8  # Is this a safe value?

            result = {}
            for f in self.entity_dofs()[entity_dim].keys():
                # Tabulate basis functions on the facet
                vals, = self.basis_evaluation(0, quad.point_set, entity=(entity_dim, f)).values()
                # Integrate the square of the basis functions on the facet.
                ints = gem.IndexSum(
                    gem.Product(gem.IndexSum(gem.Product(gem.Indexed(vals, beta + zeta),
                                                         gem.Indexed(vals, beta + zeta)), zeta),
                                quad.weight_expression),
                    quad.point_set.indices
                )
                evaluation, = evaluate([gem.ComponentTensor(ints, beta)])
                ints = evaluation.arr.flatten()
                assert evaluation.fids == ()
                result[f] = [dof for dof, i in enumerate(ints) if i > eps]

            esd[entity_dim] = result
        return esd

    def entity_support_dofs(self):
        '''Return the map of topological entities to degrees of
        freedom that have non-zero support on those entities for the
        finite element.'''
        return self._entity_support_dofs

    @abstractmethod
    def space_dimension(self):
        '''Return the dimension of the finite element space.'''

    @abstractproperty
    def index_shape(self):
        '''A tuple indicating the number of degrees of freedom in the
        element. For example a scalar quadratic Lagrange element on a triangle
        would return (6,) while a vector valued version of the same element
        would return (6, 2)'''

    @abstractproperty
    def value_shape(self):
        '''A tuple indicating the shape of the element.'''

    @property
    def fiat_equivalent(self):
        '''The FIAT element equivalent to this FInAT element.'''
        raise NotImplementedError(
            f"Cannot make equivalent FIAT element for {type(self).__name__}"
        )

    def get_indices(self):
        '''A tuple of GEM :class:`Index` of the correct extents to loop over
        the basis functions of this element.'''

        return tuple(gem.Index(extent=d) for d in self.index_shape)

    def get_value_indices(self):
        '''A tuple of GEM :class:`~gem.Index` of the correct extents to loop over
        the value shape of this element.'''

        return tuple(gem.Index(extent=d) for d in self.value_shape)

    @abstractmethod
    def basis_evaluation(self, order, ps, entity=None, coordinate_mapping=None):
        '''Return code for evaluating the element at known points on the
        reference element.

        :param order: return derivatives up to this order.
        :param ps: the point set object.
        :param entity: the cell entity on which to tabulate.
        :param coordinate_mapping: a
           :class:`~.physically_mapped.PhysicalGeometry` object that
           provides physical geometry callbacks (may be None).
        '''

    @abstractmethod
    def point_evaluation(self, order, refcoords, entity=None):
        '''Return code for evaluating the element at an arbitrary points on
        the reference element.

        :param order: return derivatives up to this order.
        :param refcoords: GEM expression representing the coordinates
                          on the reference entity.  Its shape must be
                          a vector with the correct dimension, its
                          free indices are arbitrary.
        :param entity: the cell entity on which to tabulate.
        '''

    @abstractproperty
    def mapping(self):
        '''Appropriate mapping from the reference cell to a physical cell for
        all basis functions of the finite element.'''


def entity_support_dofs(elem, entity_dim):
    '''Return the map of entity id to the degrees of freedom for which
    the corresponding basis functions take non-zero values.

    :arg elem: FInAT finite element
    :arg entity_dim: Dimension of the cell subentity.
    '''
    return elem.entity_support_dofs()[entity_dim]
